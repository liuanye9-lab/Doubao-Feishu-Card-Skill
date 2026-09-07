#!/usr/bin/env python3
"""Turn faithful plain-text event copy into an editable Card 2.0 layout spec.

This module is intentionally conservative. It does not summarize or invent
business facts. It only applies transformations that are useful for a card
surface and records each one in ``analysis.transformations`` so a person can
review the AI-to-card handoff before sending.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from content_intelligence import (
    EMOJI_ALIASES as CONTENT_EMOJI_ALIASES,
    SEMANTIC_EMOJI as CONTENT_SEMANTIC_EMOJI,
    analyze_content,
    build_image_text_items,
    build_information_allocation,
    ensure_paragraph_emoji,
    has_emoji,
    high_confidence_duplicate,
    normalize_dates,
    split_for_layout,
)
from plan_card import plan_card
from runtime_profile import (
    default_image_mode,
    image_mode_config,
    image_runtime,
)
from summary_extraction import classify_content, extract_structured_sections
from visual_spec import build_chart_plan, build_visual_spec, chart_block_from_plan, extract_metrics


ROOT = Path(__file__).resolve().parents[1]
SCENE_REGISTRY_PATH = ROOT / "scenes" / "scene-index.json"

# Intent labels for the image layer. These are metadata, not decorative
# labels: the Seedream 5.0 Pro prompt, Card compiler, and delivery report use the same
# vocabulary to explain what the bitmap is doing.
IMAGE_ROLES: Sequence[str] = (
    "cover",
    "information_carrier",
    "text_companion",
)


# Explicit aliases are safe to replace because the user has already marked
# them as icon placeholders.  The stable default is ``semantic``: it preserves
# explicit icons and adds a restrained 3–6 structural markers, never one per
# sentence or button.
EMOJI_ALIASES = {
    "[喇叭]": "📣",
    "【喇叭】": "📣",
    "[比心]": "🫶",
    "【比心】": "🫶",
    "[日历]": "📅",
    "【日历】": "📅",
    "[日程]": "🗓️",
    "【日程】": "🗓️",
    "[时间]": "⏰",
    "【时间】": "⏰",
    "[地点]": "📍",
    "【地点】": "📍",
    "[链接]": "🔗",
    "【链接】": "🔗",
    "[模板]": "🧩",
    "【模板】": "🧩",
    "[答疑]": "💬",
    "【答疑】": "💬",
    "[提交]": "🏁",
    "【提交】": "🏁",
    "[作品]": "🖼️",
    "【作品】": "🖼️",
    "[提醒]": "🔔",
    "【提醒】": "🔔",
    "[培训]": "📚",
    "【培训】": "📚",
    "[报名]": "📝",
    "【报名】": "📝",
    "[截止]": "⏳",
    "【截止】": "⏳",
    "[决赛]": "🚀",
    "【决赛】": "🚀",
    "[颁奖]": "🏆",
    "【颁奖】": "🏆",
    "[重要]": "⚠️",
    "【重要】": "⚠️",
    "[公告]": "📣",
    "【公告】": "📣",
    "[通知]": "📣",
    "【通知】": "📣",
    "[模版]": "🧩",
    "【模版】": "🧩",
    "[警告]": "⚠️",
    "【警告】": "⚠️",
    "[完成]": "✅",
    "【完成】": "✅",
}
# Keep the public symbol used by generate_card.py while making the mapping
# shared with the content-intelligence planner.
EMOJI_ALIASES.update(CONTENT_EMOJI_ALIASES)

SEMANTIC_EMOJI = CONTENT_SEMANTIC_EMOJI

def load_scene_rules() -> List[Tuple[str, str, Tuple[str, ...]]]:
    try:
        registry = json.loads(SCENE_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError(f"cannot load scene registry: {exc}") from exc
    rules: List[Tuple[str, str, Tuple[str, ...]]] = []
    for item in registry.get("scenes", []):
        if not isinstance(item, dict):
            continue
        scene_id = item.get("id")
        card_type = item.get("type") or "custom"
        keywords = tuple(keyword for keyword in item.get("keywords", []) if isinstance(keyword, str) and keyword.strip())
        if isinstance(scene_id, str) and keywords:
            rules.append((scene_id, card_type, keywords))
    return rules


BUTTON_LABEL_RULES: Sequence[Tuple[Tuple[str, ...], str]] = (
    (("报名", "注册", "参加"), "立即报名"),
    (("查看作品", "打开作品", "作品详情"), "查看作品"),
    (("提交", "交付", "作品"), "提交作品"),
    (("培训", "课程", "教程"), "查看培训"),
    (("模板", "模版", "下载"), "下载模板"),
    (("评审", "评分", "结果"), "查看详情"),
    (("查看", "详情", "了解"), "查看详情"),
)

URL_RE = re.compile(r"(?P<url>(?:https?://|lark://|feishu://)[^\s<>\"'“”‘’]+)", re.I)
IMAGE_MARKER_RE = re.compile(r"!\[(?P<alt>[^]]*)\]\((?P<source>[^)]+)\)")
LINK_MODES = {"button", "inline"}
MEDIA_HINT_RE = re.compile(r"首图|配图|海报|图片|图文|动图|GIF|动画|轮播|切换图片|图片切换|上一张|下一张|carousel|image[- ]?switch", re.I)
MEDIA_SWITCH_RE = re.compile(r"轮播|切换图片|图片切换|图集切换|上一张|下一张|carousel|image[- ]?switch", re.I)
MEDIA_EXTENSION_RE = re.compile(r"\.(?:gif|png|jpe?g|webp|avif)(?:[?#].*)?$", re.I)
HIGHLIGHT_SECTION_RE = re.compile(
    r"核心价值|一句话价值|为什么值得看|关键结论|结论|重点|亮点|结果|注意|提醒|风险|当前阶段|下一步|行动建议"
)
# Native text surfaces are intentionally more structured than the legacy
# "one heading + one naked paragraph" output.  The image is still the visual
# entrance; everything underneath it that carries prose should be an editable
# native highlight surface with a small, deterministic hierarchy marker.
TEXT_SURFACE_POLICY = "highlight-first"
HIERARCHY_TITLE_PREFIX = "—"
HIERARCHY_ITEM_PREFIX = "•"
TEXT_LABEL_RE = re.compile(r"^\s*(?P<label>[^：:]{1,24})\s*[：:]\s*(?P<body>.+?)\s*$")
FULL_DATE_ATOM = r"(?:20\d{2}[年./-])?(?:\d{1,2}月(?:\d{1,2}(?:日|号)?|初|上旬|中旬|下旬|底|中)|\d{1,2}[./-]\d{1,2})"
FULL_DATE_RANGE_RE = re.compile(
    rf"(?P<start>{FULL_DATE_ATOM})\s*(?P<separator>[-—~～至到])\s*(?P<end>{FULL_DATE_ATOM})"
)
COMPACT_DATE_RANGE_RE = re.compile(
    r"(?<!\d)(?P<sm>0?[1-9]|1[0-2])(?P<sd>0?[1-9]|[12]\d|3[01])\s*(?P<separator>[-—~～至到])\s*(?P<em>0?[1-9]|1[0-2])(?P<ed>0?[1-9]|[12]\d|3[01])(?!\d)"
)
MONTH_ONLY_RE = re.compile(r"(?<!\d)(?P<m>0?[1-9]|1[0-2])月(?P<qual>初|上旬|中旬|下旬|底|中)(?!\d)")
FULL_DATE_RE = re.compile(rf"(?P<date>{FULL_DATE_ATOM})")
NUMERIC_DATE_RE = re.compile(r"(?<!\d)(?P<m>0?[1-9]|1[0-2])(?P<d>0?[1-9]|[12]\d|3[01])(?!\d)")
FACT_RE = re.compile(r"^\s*(?P<label>公司|部门|智能体方向|当前状态|时间|日期|地点|对象|形式|主题|状态|负责人|联系人|活动时间|培训时间|截止时间|报名时间|提交时间)\s*[：:]\s*(?P<value>.+?)\s*$")
HEADING_RE = re.compile(r"^\s*(?P<marker>#{1,4}\s+|【(?P<bracket>[^】]+)】\s*)?(?P<title>.+?)\s*$")
LIST_MARKER_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)、])\s*")
STEP_LINE_RE = re.compile(
    r"^\s*(?:(?:第\s*(?P<cn>[一二三四五六七八九十]+)\s*步)|(?:步骤\s*(?P<step_num>\d+))|(?:step\s*(?P<en>\d+))|(?P<num>\d+)\s*[.)、])\s*[：:.)、-]?\s*(?P<title>.+?)\s*$",
    re.I,
)
CHINESE_NUMBERS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
SIMILARITY_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9]+")
GENERIC_DATE_PREFIXES = {"请于", "于", "在", "从", "自", "截至", "截止"}


def normalize_emoji_aliases(value: Any) -> Any:
    """Replace only explicit icon aliases, recursively, without rewriting prose."""
    if isinstance(value, str):
        for alias, emoji in EMOJI_ALIASES.items():
            value = value.replace(alias, emoji)
        return value
    if isinstance(value, list):
        return [normalize_emoji_aliases(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_emoji_aliases(item) for key, item in value.items()}
    return value


def compact_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def body_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return str(value or "")


def split_text_label(value: Any) -> Tuple[str, str]:
    """Split a source-backed ``label：body`` line without rewriting facts."""
    text = str(value or "").strip()
    match = TEXT_LABEL_RE.match(text)
    if not match:
        return "", text
    label = compact_text(match.group("label"))
    body = str(match.group("body") or "").strip()
    if not label or not body or URL_RE.match(body):
        return "", text
    return label, body


def text_surface_tone(title: Any, *, role: str = "module") -> str:
    """Choose a restrained native surface from source semantics."""
    value = compact_text(title)
    if re.search(r"风险|注意|提醒|截止|必须|警告|逾期", value):
        return "warning"
    if re.search(r"结果|价值|结论|完成|亮点|成果", value):
        return "success"
    if role == "lead":
        return "info"
    return "brand"


def clean_url(url: str) -> str:
    return url.rstrip("。，、；;：:）)】]}>\"'．")


def semantic_marker(text: str) -> str:
    """Prefix a short derived label with at most one semantic Emoji."""
    value = text.strip()
    if not value or any(char in value for char in "📣🫶📅🗓️⏰📍🔗🧩💬🏁🖼️🔔📚📝⏳🚀🏆⚠️"):
        return value
    for keywords, emoji in SEMANTIC_EMOJI:
        if any(keyword in value for keyword in keywords):
            return f"{emoji} {value}"
    return value


def _valid_date(month: int, day: int) -> bool:
    return 1 <= month <= 12 and 1 <= day <= 31


def _format_date_atom(atom: str) -> Optional[str]:
    raw = atom.strip()
    month_only = MONTH_ONLY_RE.fullmatch(raw)
    if month_only:
        return f"{int(month_only.group('m'))}月{month_only.group('qual')}"
    year_match = re.fullmatch(r"20\d{2}[年./-](\d{1,2})[月./-](\d{1,2})(?:日|号)?", raw)
    if year_match:
        month, day = int(year_match.group(1)), int(year_match.group(2))
        return f"{month}月{day}日" if _valid_date(month, day) else None
    chinese_match = re.fullmatch(r"(\d{1,2})月(\d{1,2})(?:日|号)?", raw)
    if chinese_match:
        month, day = int(chinese_match.group(1)), int(chinese_match.group(2))
        return f"{month}月{day}日" if _valid_date(month, day) else None
    numeric_match = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})", raw)
    if numeric_match:
        month, day = int(numeric_match.group(1)), int(numeric_match.group(2))
        return f"{month}月{day}日" if _valid_date(month, day) else None
    compact_match = re.fullmatch(r"(\d{2})(\d{2})", raw)
    if compact_match:
        month, day = int(compact_match.group(1)), int(compact_match.group(2))
        return f"{month}月{day}日" if _valid_date(month, day) else None
    return None


def find_date_info(line: str) -> Optional[Dict[str, Any]]:
    compact_range = COMPACT_DATE_RANGE_RE.search(line)
    if compact_range:
        start = f"{int(compact_range.group('sm')):02d}{int(compact_range.group('sd')):02d}"
        end = f"{int(compact_range.group('em')):02d}{int(compact_range.group('ed')):02d}"
        display = f"{int(compact_range.group('sm'))}月{int(compact_range.group('sd'))}日—{int(compact_range.group('em'))}月{int(compact_range.group('ed'))}日"
        return {"source": compact_range.group(0), "display": display, "start": compact_range.start(), "end": compact_range.end(), "kind": "compact_range", "parts": [start, end]}

    full_range = FULL_DATE_RANGE_RE.search(line)
    if full_range:
        start_display = _format_date_atom(full_range.group("start"))
        end_display = _format_date_atom(full_range.group("end"))
        if start_display and end_display:
            return {"source": full_range.group(0), "display": f"{start_display}—{end_display}", "start": full_range.start(), "end": full_range.end(), "kind": "range", "parts": [full_range.group("start"), full_range.group("end")]}

    month_only = MONTH_ONLY_RE.search(line)
    if month_only:
        return {"source": month_only.group(0), "display": _format_date_atom(month_only.group(0)), "start": month_only.start(), "end": month_only.end(), "kind": "month_only", "parts": [month_only.group(0)]}

    full = FULL_DATE_RE.search(line)
    if full:
        display = _format_date_atom(full.group("date"))
        if display:
            return {"source": full.group("date"), "display": display, "start": full.start(), "end": full.end(), "kind": "date", "parts": [full.group("date")]}

    numeric = NUMERIC_DATE_RE.search(line)
    if numeric:
        raw = numeric.group(0)
        display = _format_date_atom(raw)
        if display:
            return {"source": raw, "display": display, "start": numeric.start(), "end": numeric.end(), "kind": "compact", "parts": [raw]}
    return None


def _chinese_step_number(value: str) -> Optional[int]:
    if not value:
        return None
    if value in CHINESE_NUMBERS:
        return CHINESE_NUMBERS[value]
    if value.startswith("十"):
        return 10 + CHINESE_NUMBERS.get(value[1:], 0)
    if value.endswith("十"):
        return CHINESE_NUMBERS.get(value[:-1], 0) * 10
    if "十" in value:
        tens, ones = value.split("十", 1)
        return CHINESE_NUMBERS.get(tens, 0) * 10 + CHINESE_NUMBERS.get(ones, 0)
    return None


def parse_step_line(line: str) -> Optional[Dict[str, Any]]:
    """Parse explicit Chinese/English ordered steps without inventing content."""
    match = STEP_LINE_RE.match(line)
    if not match:
        return None
    raw_number = match.group("step_num") or match.group("en") or match.group("num")
    number = int(raw_number) if raw_number else _chinese_step_number(match.group("cn") or "")
    if not number:
        return None
    title = match.group("title").strip()
    if not title:
        return None
    return {"date": f"步骤 {number}", "title": title, "source_text": line, "source_lines": [line]}


def _step_context(current: Optional[Dict[str, Any]], blocks: Sequence[Dict[str, Any]]) -> bool:
    """Require flow language before treating a numbered list as a timeline."""
    context: List[str] = []
    if isinstance(current, dict):
        context.extend(str(current.get(key) or "") for key in ("title", "body"))
    for block in blocks[-3:]:
        if isinstance(block, dict):
            context.extend(str(block.get(key) or "") for key in ("title", "content", "source_text"))
    return bool(re.search(r"步骤|流程|阶段|时间线|日程|节点|step|phase|timeline", " ".join(context), re.I))


def _strip_list_marker(value: str) -> str:
    return LIST_MARKER_RE.sub("", value, count=1).strip()


def split_timeline_line(line: str, date_info: Dict[str, Any]) -> Dict[str, Any]:
    before = line[: int(date_info["start"])].strip(" \t：:|·•-—")
    raw_after = line[int(date_info["end"]):]
    suffix_match = re.match(r"\s*(前|后|起)", raw_after)
    temporal_suffix = suffix_match.group(1) if suffix_match else ""
    after = raw_after[suffix_match.end():] if suffix_match else raw_after
    after = after.strip(" \t：:|·•-—，,、。；;")
    before = _strip_list_marker(before)
    before_without_marker = re.sub(r"^[📣🫶📅🗓️⏰📍🔗🧩💬🏁🖼️🔔📚📝⏳🚀🏆⚠️✅💡✨🎓📄 ]+", "", before)
    title = before if before and before_without_marker not in {"时间", "日期", "活动时间", "报名时间", "提交时间", *GENERIC_DATE_PREFIXES} else ""
    body = ""
    after = re.sub(r"^(?:前|后|起|开始|截止)\s*[，,：:、 ]*", "", after)
    date_range_suffix = ""
    if not before and re.fullmatch(r"(?:本)?(?:月底|九月底|年末|年底|上旬|中旬|下旬)", after):
        date_range_suffix = f"—{after}"
        after = ""
    # A clock value is not a label/value separator. Without this guard,
    # ``9月4日 14:00 开始`` is incorrectly split at the colon into title
    # ``14`` and body ``00 开始``. Keep the complete time in the milestone.
    if re.match(r"^\d{1,2}:\d{2}(?:\s|$)", after):
        title = after
        body = ""
    elif not title and after:
        parts = re.split(r"[：:。；;，,]", after, maxsplit=1)
        title = parts[0].strip()
        body = parts[1].strip() if len(parts) > 1 and parts[1].strip() else ""
    elif title and after:
        body = after
    # Do not invent a stage name when the source only contains a date.  A
    # date-only milestone is still a useful, fully faithful timeline row.
    if not title:
        title = ""
    return {
        "date": f"{date_info['display']}{temporal_suffix}{date_range_suffix}",
        "title": title,
        **({"body": body} if body else {}),
        "source_text": line,
        "source_lines": [line],
    }


DIRECT_SEEDREAM_MODE = "seedream_5_pro_direct_full_card"
DIRECT_SEEDREAM_TEXT_MODE = "seedream_5_pro_direct_selected_text_and_layout"
BANNER_SEEDREAM_MODE = "seedream_5_pro_banner_plus_native_card"
BANNER_SEEDREAM_TEXT_MODE = "seedream_5_pro_banner_selected_text_and_layout"
SUPPORTED_IMAGE_MODES = (DIRECT_SEEDREAM_MODE, BANNER_SEEDREAM_MODE)


def _image_mode_config(mode: str) -> Dict[str, Any]:
    """Read the shared Doubao image mode profile with a stable fallback."""
    try:
        return image_mode_config(mode)
    except ValueError:
        if mode == DIRECT_SEEDREAM_MODE:
            return {
                "text_policy": DIRECT_SEEDREAM_TEXT_MODE,
                "roles": list(IMAGE_ROLES),
            }
        if mode == BANNER_SEEDREAM_MODE:
            return {
                "text_policy": BANNER_SEEDREAM_TEXT_MODE,
                "roles": ["banner", "information_carrier", "text_companion"],
            }
        raise


def _default_image_mode() -> str:
    try:
        mode = default_image_mode()
    except ValueError:
        mode = DIRECT_SEEDREAM_MODE
    return mode if mode in SUPPORTED_IMAGE_MODES else DIRECT_SEEDREAM_MODE


def _runtime_model() -> Tuple[str, str]:
    try:
        runtime = image_runtime()
    except ValueError:
        runtime = {}
    return (
        str(runtime.get("generation_model") or "seedream-5.0-pro"),
        str(runtime.get("generation_model_label") or "Seedream 5.0 Pro"),
    )


def build_image_text_checklist(
    blocks: Sequence[Dict[str, Any]],
    title: str,
    *,
    allocation: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Return the allocated Seedream 5.0 Pro text, never the whole Card copy."""
    if isinstance(allocation, Mapping):
        image = allocation.get("image")
        if isinstance(image, Mapping) and isinstance(image.get("include"), list):
            return [item for item in image["include"] if isinstance(item, dict)]
    return build_image_text_items(blocks, title)


def _is_heading(line: str) -> Optional[str]:
    value = line.strip()
    if not value:
        return None
    if value.startswith("#"):
        return value.lstrip("#").strip()
    bracket = re.fullmatch(r"【([^】]+)】", value)
    if bracket:
        return bracket.group(1).strip()
    if len(value) <= 28 and value.endswith(("：", ":")):
        return value[:-1].strip()
    return None


def _fact(line: str) -> Optional[Dict[str, str]]:
    match = FACT_RE.match(line.lstrip("📅🗓️⏰📍🔗🧩💬🏁🖼️🔔📚📝⏳🚀🏆⚠️ "))
    if not match:
        return None
    return {"label": match.group("label"), "value": match.group("value").strip()}


def _token_set(value: str) -> set[str]:
    return set(SIMILARITY_TOKEN_RE.findall(value.lower()))


def _similarity(left: str, right: str) -> float:
    a, b = _token_set(left), _token_set(right)
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


_CASE_HEADING_GROUPS = {
    "context": ("背景", "问题", "挑战"),
    "method": ("做法", "方法", "方案", "实现"),
    "result": ("结果", "成效", "状态", "覆盖"),
    "reuse": ("进阶构思", "可复用经验", "为什么值得看", "案例价值"),
}
_RESULT_TITLE_HINTS = ("结果", "获奖", "颁奖", "排名")
_GENERIC_RESULT_KEYWORDS = {"结果"}


def _case_structure_signal(text: str) -> List[str]:
    """Return case-study structure labels found in source-like headings.

    A generic word such as ``结果`` is too weak to decide that a card is a
    post-event announcement.  Two or more source headings that describe a
    context/method/result relationship are a much stronger, deterministic
    case-study signal and therefore win before registry keyword scoring.
    """
    labels: List[str] = []
    for line in text.splitlines():
        value = line.strip().lstrip("# ")
        if not value:
            continue
        label = re.split(r"[：:]", value, maxsplit=1)[0].strip()
        for group in _CASE_HEADING_GROUPS.values():
            if label in group and label not in labels:
                labels.append(label)
                break
    return labels


def infer_scene(text: str, explicit_scene: Optional[str] = None) -> Tuple[Optional[str], Optional[str], List[Dict[str, Any]]]:
    rules = load_scene_rules()
    if explicit_scene:
        for scene_id, card_type, _ in rules:
            if scene_id == explicit_scene:
                return explicit_scene, card_type, []
        raise ValueError(f"unknown scene: {explicit_scene}")
    value = text.lower()
    title = next((line.strip().lstrip("# ") for line in text.splitlines() if line.strip()), "").lower()
    case_labels = _case_structure_signal(text)
    if len(case_labels) >= 2 and any(label in _CASE_HEADING_GROUPS["method"] + _CASE_HEADING_GROUPS["result"] for label in case_labels):
        return "case-showcase", "story", [{
            "kind": "scene_inference",
            "scene": "case-showcase",
            "matched_keywords": case_labels,
            "precedence": "case_structure_over_generic_keyword",
            "reason": "至少两个来源层级标题形成背景/做法/结果关系，优先按作品案例展示处理",
        }]
    scores: List[Tuple[int, int, str, str, Tuple[str, ...]]] = []
    for index, (scene_id, card_type, keywords) in enumerate(rules):
        matched = [keyword for keyword in keywords if keyword.lower() in value]
        score = sum(value.count(keyword.lower()) for keyword in keywords)
        # ``结果`` alone is a common field label inside a case, report, or
        # product brief.  It must not outrank an otherwise custom card unless
        # the title or a second result signal makes the announcement intent
        # explicit.  This keeps keyword routing deterministic without
        # requiring every caller to pass ``--scene``.
        if scene_id == "result-announcement" and matched and set(matched).issubset(_GENERIC_RESULT_KEYWORDS):
            if not any(hint in title for hint in _RESULT_TITLE_HINTS) and score < 2:
                continue
        if score:
            scores.append((score, -index, scene_id, card_type, keywords))
    if not scores:
        return None, "custom", []
    _, _, scene_id, card_type, keywords = sorted(scores, reverse=True)[0]
    return scene_id, card_type, [{"kind": "scene_inference", "scene": scene_id, "matched_keywords": [keyword for keyword in keywords if keyword.lower() in value]}]


def scene_default_preset(scene_id: Optional[str]) -> Optional[str]:
    if not scene_id or not SCENE_REGISTRY_PATH.exists():
        return None
    try:
        import json

        registry = json.loads(SCENE_REGISTRY_PATH.read_text(encoding="utf-8"))
        for item in registry.get("scenes", []):
            if isinstance(item, dict) and item.get("id") == scene_id:
                return item.get("default_preset")
    except (OSError, ValueError, TypeError):
        return None
    return None


def canonical_template_id(value: Optional[str]) -> Optional[str]:
    """Resolve a scene/legacy preset ID to the current production template."""
    candidate = str(value or "").strip()
    if not candidate:
        return None
    try:
        registry = json.loads((ROOT / "presets" / "preset-index.json").read_text(encoding="utf-8"))
        aliases = registry.get("aliases") if isinstance(registry.get("aliases"), dict) else {}
        return str(aliases.get(candidate) or candidate)
    except (OSError, ValueError, TypeError):
        return candidate


def infer_button_label(context: str) -> str:
    for keywords, label in BUTTON_LABEL_RULES:
        if any(keyword in context for keyword in keywords):
            return label
    return "打开链接"


def extract_urls(
    lines: Iterable[str],
    *,
    excluded_urls: Optional[set[str]] = None,
    allowed_urls: Optional[set[str]] = None,
    button_labels: Optional[Mapping[str, str]] = None,
) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
    links: List[Dict[str, str]] = []
    transformations: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for line in lines:
        for match in URL_RE.finditer(line):
            url = clean_url(match.group("url"))
            if not url or url in seen or (excluded_urls and url in excluded_urls) or (allowed_urls is not None and url not in allowed_urls):
                continue
            seen.add(url)
            context = line.replace(match.group("url"), " ")
            links.append({
                "text": (button_labels or {}).get(url) or infer_button_label(context),
                "url": url,
                "style": "primary" if not links else "secondary",
            })
            transformations.append({"kind": "link_to_button", "source": url, "button_text": links[-1]["text"]})
    return links, transformations


def extract_media_sources(lines: Iterable[str]) -> List[Dict[str, Any]]:
    """Find image-like source URLs without treating them as action buttons."""
    sources: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for line in lines:
        markers = list(IMAGE_MARKER_RE.finditer(line))
        line_has_media_hint = bool(MEDIA_HINT_RE.search(line))
        for marker in markers:
            source = clean_url(marker.group("source").strip())
            if not source or source in seen:
                continue
            seen.add(source)
            sources.append({
                "kind": "gif" if MEDIA_EXTENSION_RE.search(source) and source.lower().split("?", 1)[0].endswith(".gif") else "image",
                "source": source,
                "alt": marker.group("alt").strip() or "卡片配图",
                "source_text": line,
            })
        if line_has_media_hint:
            for match in URL_RE.finditer(line):
                source = clean_url(match.group("url"))
                if not source or source in seen:
                    continue
                seen.add(source)
                is_gif = bool(re.search(r"GIF|动图|动画", line, re.I) or (MEDIA_EXTENSION_RE.search(source) and source.lower().split("?", 1)[0].endswith(".gif")))
                sources.append({
                    "kind": "gif" if is_gif else "image",
                    "source": source,
                    "alt": "动图" if is_gif else "活动配图",
                    "source_text": line,
                })
    return sources


def route_link_text(
    lines: Sequence[str],
    transformations: List[Dict[str, Any]],
    mode: str,
    *,
    media_urls: Optional[set[str]] = None,
    button_urls: Optional[set[str]] = None,
) -> List[str]:
    """Keep a link's meaning visible without printing the same URL twice."""
    if mode not in LINK_MODES:
        raise ValueError("link_mode must be button or inline")
    if mode == "inline":
        routed: List[str] = []
        for line in lines:
            rendered = IMAGE_MARKER_RE.sub(lambda match: match.group("alt").strip(), line)
            if media_urls:
                rendered = URL_RE.sub(
                    lambda match: "" if clean_url(match.group("url")) in media_urls else match.group("url"),
                    rendered,
                )
            if rendered != line:
                transformations.append({
                    "kind": "media_visual_route" if media_urls and any(clean_url(match.group("url")) in media_urls for match in URL_RE.finditer(line)) else "image_marker_visual_route",
                    "source": line,
                    "output": rendered,
                    "display": "asset_plan" if media_urls and any(clean_url(match.group("url")) in media_urls for match in URL_RE.finditer(line)) else "alt_text_only",
                })
            routed.append(rendered)
        return routed

    routed: List[str] = []
    for line in lines:
        if not URL_RE.search(line) and not IMAGE_MARKER_RE.search(line):
            routed.append(line)
            continue
        rendered = IMAGE_MARKER_RE.sub(lambda match: match.group("alt").strip(), line)
        rendered = URL_RE.sub(
            lambda match: "" if (
                clean_url(match.group("url")) in (button_urls or set())
                or (media_urls and clean_url(match.group("url")) in media_urls)
            ) else match.group("url"),
            rendered,
        )
        rendered = re.sub(r"\s+", " ", rendered).strip()
        # A label such as “提交入口：https://…” should not leave a dangling
        # colon after the URL has moved into the button behavior.
        rendered = re.sub(r"([：:])\s*$", "", rendered).strip()
        rendered = re.sub(r"([，,；;])\s*$", "", rendered).strip()
        matched_urls = {clean_url(match.group("url")) for match in URL_RE.finditer(line)}
        is_media_route = bool(media_urls and matched_urls & media_urls)
        transformations.append({
            "kind": "media_visual_route" if is_media_route else ("link_visual_route" if URL_RE.search(line) else "image_marker_visual_route"),
            "source": line,
            "output": rendered,
            "display": "asset_plan" if is_media_route else ("button_only" if button_urls and matched_urls & button_urls else "inline_url_preserved"),
        })
        if rendered:
            routed.append(rendered)
    return routed


def _empty_block(block_type: str) -> Dict[str, Any]:
    if block_type == "text":
        return {"type": "text", "content": ""}
    if block_type == "section":
        return {"type": "section", "title": "", "body": ""}
    if block_type == "facts":
        return {"type": "facts", "items": []}
    if block_type == "timeline":
        return {"type": "timeline", "items": [], "timeline_focus": True, "timeline_date_bold": True, "show_title": False}
    raise ValueError(f"unsupported auto block type: {block_type}")


def build_blocks(
    lines: Sequence[str],
    transformations: List[Dict[str, Any]],
    *,
    emoji_mode: str = "semantic",
    scene: Optional[str] = None,
) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    existing_emoji_count = sum(
        len(re.findall(r"[\U0001F1E6-\U0001FAFF\u2300-\u27BF]", str(line or "")))
        for line in lines
    )
    semantic_budget = [max(0, 6 - existing_emoji_count) if emoji_mode == "semantic" else 0]

    def mark_paragraph(line: str) -> str:
        # Ordinary copy stays clean unless it contains a clear semantic cue
        # such as 查看/提交/风险.  This lets a very short card receive one
        # useful scan anchor without decorating every sentence.
        if emoji_mode != "semantic" or semantic_budget[0] <= 0:
            return line
        marker = next(
            (emoji for keywords, emoji in SEMANTIC_EMOJI if any(word.lower() in line.lower() for word in keywords)),
            None,
        )
        if not marker or has_emoji(line):
            return line
        semantic_budget[0] -= 1
        marked = f"{marker} {line}"
        transformations.append({"kind": "paragraph_emoji", "source": line, "output": marked, "emoji": marker, "reason": "clear semantic cue within the card Emoji budget"})
        return marked

    def mark_structural(value: str, kind: str) -> str:
        if emoji_mode != "semantic" or semantic_budget[0] <= 0:
            return value
        marked, emoji = ensure_paragraph_emoji(value, enabled=True)
        if emoji:
            semantic_budget[0] -= 1
            transformations.append({
                "kind": kind,
                "source": value,
                "output": marked,
                "emoji": emoji,
                "reason": "semantic structural marker within the 3–6 Emoji card budget",
            })
        return marked

    def flush() -> None:
        nonlocal current
        if not current:
            return
        if current.get("type") == "text" and not compact_text(current.get("content")):
            current = None
            return
        if current.get("type") == "section" and not compact_text(current.get("title")) and not compact_text(current.get("body")):
            current = None
            return
        if current.get("type") == "facts" and not current.get("items"):
            current = None
            return
        if current.get("type") == "timeline" and not current.get("items"):
            current = None
            return
        blocks.append(current)
        current = None

    for line in lines:
        if not compact_text(line):
            # Button-only URL routing can leave an aligned empty placeholder;
            # ignore it here without changing source/rendered line pairing.
            continue
        fact = _fact(line)
        if fact:
            fact["label"] = mark_structural(fact["label"], "fact_emoji")
            fact["source_text"] = line
            if current and current.get("type") == "facts":
                current["items"].append(fact)
            else:
                flush()
                current = _empty_block("facts")
                current["items"].append(fact)
            continue

        if scene == "case-showcase":
            # The native button already carries this destination. Removing
            # the leftover label keeps the content flow clean while the
            # source URL remains preserved in the button contract.
            if re.fullmatch(r"(?:初赛)?作品链接", line.strip()):
                transformations.append({
                    "kind": "case_link_label_suppressed",
                    "source": line,
                    "output": "native 查看作品 button",
                    "reason": "链接已由原生按钮承载，不再保留孤立标签",
                })
                continue
            participant = re.match(r"^\s*选手\s*[：:]\s*.+$", line)
            if participant:
                flush()
                current = {
                    "type": "text",
                    "content": line,
                    "text_size": "heading",
                    "source_text": line,
                }
                continue
            if re.fullmatch(r"案例拆解(?:（.*）|\(.*\))", line.strip()):
                flush()
                current = {
                    "type": "div",
                    "content": line,
                    "text_size": "notation",
                    "text_color": "grey",
                    "source_text": line,
                }
                flush()
                transformations.append({
                    "kind": "case_source_note_deemphasis",
                    "source": line,
                    "output": "notation",
                    "reason": "保留来源说明，但降低视觉权重，避免抢占案例正文层级",
                })
                continue
            case_section = re.match(
                r"^\s*(?P<title>背景(?:/[^：:]+)?|做法|结果(?:/价值)?)\s*[：:]\s*(?P<body>.*?)\s*$",
                line,
            )
            if case_section:
                flush()
                current = _empty_block("section")
                current["title"] = mark_structural(case_section.group("title"), "case_section_emoji")
                current["source_title"] = line
                body = case_section.group("body").strip()
                if body:
                    parts = split_for_layout(body)
                    if len(parts) > 1:
                        transformations.append({
                            "kind": "long_text_split",
                            "source": line,
                            "output": parts,
                            "reason": "案例正文按句子/显示长度拆分，未改写或丢弃原文",
                        })
                    for part in parts:
                        current["body"] = f"{current.get('body', '')}\n{part}".strip()
                        current.setdefault("source_lines", []).append(line)
                continue

        step_item = parse_step_line(line)
        if step_item and not re.match(r"^\s*(?:第\s*[一二三四五六七八九十]+\s*步|步骤\s*\d+|step\s*\d+)", line, re.I) and not _step_context(current, blocks):
            # Plain numbered content such as “本群内我们会 1.… 2.…” is a
            # checklist/list, not an invented timeline. Explicit step words
            # or nearby flow language are required for the timeline parser.
            step_item = None
        if (
            scene == "case-showcase"
            and step_item
            and current
            and current.get("type") == "section"
            and compact_text(current.get("title")) == "做法"
        ):
            # Numbered methods belong to the case's method section. A single
            # phrase such as “操作流程” must not turn one method into a
            # misleading timeline row.
            current["body"] = f"{current.get('body', '')}\n{line.strip()}".strip()
            current.setdefault("source_lines", []).append(line)
            transformations.append({
                "kind": "case_method_list_kept_in_section",
                "source": line,
                "output": "做法 section",
                "reason": "案例编号表示并列做法，不表示时间或阶段变化",
            })
            continue
        if step_item:
            flush()
            if blocks and blocks[-1].get("type") == "timeline" and blocks[-1].get("_adjacent"):
                blocks[-1]["items"].append(step_item)
            else:
                current = _empty_block("timeline")
                current["_adjacent"] = True
                current["items"].append(step_item)
                flush()
            transformations.append({"kind": "step_to_timeline", "source": line, "step_label": step_item["date"], "title": step_item["title"]})
            continue

        date_info = find_date_info(line)
        if date_info:
            if blocks and blocks[-1].get("type") == "timeline" and blocks[-1].get("_adjacent") and LIST_MARKER_RE.match(line):
                milestones = blocks[-1].get("items") if isinstance(blocks[-1].get("items"), list) else []
                if milestones:
                    # A dated bullet immediately below a date/range heading is
                    # a detail of that milestone (for example, two training
                    # dates inside ``8月24日—9月4日``), not a new top-level
                    # milestone. Keep the original dated line verbatim.
                    milestone = milestones[-1]
                    detail = line.strip()
                    existing = str(milestone.get("body") or "").strip()
                    milestone["body"] = f"{existing}\n{detail}".strip() if existing else detail
                    source_lines = milestone.setdefault("source_lines", [])
                    if isinstance(source_lines, list):
                        source_lines.append(line)
                    transformations.append({
                        "kind": "timeline_detail_group",
                        "source": line,
                        "output": "attached to the preceding dated milestone",
                        "reason": "dated bullet details stay visually grouped with their date",
                    })
                    continue
            flush()
            timeline_item = split_timeline_line(line, date_info)
            if timeline_item.get("title"):
                timeline_item["title"] = mark_structural(timeline_item["title"], "timeline_emoji")
            if date_info.get("source") != timeline_item.get("date"):
                transformations.append({"kind": "date_normalize", "source": date_info["source"], "output": timeline_item["date"], "source_text": line})
            if blocks and blocks[-1].get("type") == "timeline" and blocks[-1].get("_adjacent"):
                blocks[-1]["items"].append(timeline_item)
            else:
                current = _empty_block("timeline")
                current["_adjacent"] = True
                current["items"].append(timeline_item)
                flush()
            continue

        if blocks and blocks[-1].get("type") == "timeline":
            timeline_block = blocks[-1]
            milestones = timeline_block.get("items") if isinstance(timeline_block.get("items"), list) else []
            # A date-only row is commonly followed by bullet items in a plain
            # brief. Keep those items inside the same visual milestone so the
            # rendered timeline carries the relationship instead of producing
            # a detached paragraph below it.
            if milestones and timeline_block.get("_adjacent") and LIST_MARKER_RE.match(line):
                milestone = milestones[-1]
                detail = line.strip()
                raw_existing = milestone.get("body", "")
                existing = "\n".join(str(item) for item in raw_existing) if isinstance(raw_existing, list) else str(raw_existing or "")
                existing = existing.strip()
                milestone["body"] = f"{existing}\n{detail}".strip() if existing else detail
                source_lines = milestone.setdefault("source_lines", [])
                if isinstance(source_lines, list):
                    source_lines.append(line)
                transformations.append({
                    "kind": "timeline_detail_group",
                    "source": line,
                    "output": "attached to the preceding dated milestone",
                    "reason": "bullet details stay visually grouped with their date",
                })
                continue
            timeline_block["_adjacent"] = False

        if current and current.get("type") == "timeline":
            current.pop("_adjacent", None)
            flush()

        heading = _is_heading(line)
        if heading:
            flush()
            marked_heading = mark_structural(heading, "heading_emoji")
            current = _empty_block("section")
            current["title"] = marked_heading
            current["source_title"] = line
            continue

        if current and current.get("type") == "section":
            parts = split_for_layout(line)
            if len(parts) > 1:
                transformations.append({
                    "kind": "long_text_split",
                    "source": line,
                    "output": parts,
                    "reason": "按句子/显示长度拆分，未改写或丢弃原文",
                })
            for part in parts:
                marked = mark_paragraph(part)
                current["body"] = f"{current.get('body', '')}\n{marked}".strip()
                current.setdefault("source_lines", []).append(line)
            continue

        if LIST_MARKER_RE.match(line) and blocks and blocks[-1].get("type") == "text":
            # Turn a short preceding introduction into a section heading so a
            # numbered/bulleted group reads as one visual information block.
            previous = blocks.pop()
            current = {
                "type": "section",
                "title": previous.get("content", ""),
                "body": line,
                "source_title": previous.get("source_text"),
                "source_lines": [line],
            }
            continue

        # One source line becomes one visual paragraph.  This prevents a long
        # input from becoming a single wall of text and keeps the source span
        # available for a human audit after an Emoji marker is added.
        parts = split_for_layout(line)
        if len(parts) > 1:
            transformations.append({
                "kind": "long_text_split",
                "source": line,
                "output": parts,
                "reason": "按句子/显示长度拆分，未改写或丢弃原文",
            })
        for part in parts:
            flush()
            marked = mark_paragraph(part)
            if re.search(r"截止|最后|请务必|必须|重要|今日", line) and len(line) <= 100:
                current = {
                    "type": "highlight",
                    "content": marked,
                    "source_text": line,
                    "text_size": "normal_v2",
                    "tone": "danger",
                    "attention": "alert",
                }
                transformations.append({"kind": "attention_color", "source_text": line, "output": "danger highlight block"})
            else:
                current = {"type": "text", "content": marked, "source_text": line}

    flush()
    for block in blocks:
        block.pop("_adjacent", None)
        block.pop("source_title", None)
    return blocks


def _remove_source_lines(blocks: List[Dict[str, Any]], source_lines: set[str]) -> List[Dict[str, Any]]:
    """Remove lines promoted to structured components without changing their text."""
    result: List[Dict[str, Any]] = []
    for block in blocks:
        item = dict(block)
        source_text = item.get("source_text")
        if isinstance(source_text, str) and source_text.strip() in source_lines:
            # A paragraph that was promoted to a fact/timeline/button must not
            # remain as a second copy merely because the rendered paragraph has
            # a semantic Emoji prefix.
            continue
        field = "content" if item.get("type") in {"text", "div"} else "body" if item.get("type") == "section" else None
        if field and isinstance(item.get(field), str):
            source_group = item.get("source_lines") if isinstance(item.get("source_lines"), list) else []
            rendered_lines = item[field].splitlines()
            if source_group and len(source_group) == len(rendered_lines):
                kept = [
                    rendered_line
                    for rendered_line, original_line in zip(rendered_lines, source_group)
                    if not isinstance(original_line, str) or original_line.strip() not in source_lines
                ]
            else:
                kept = [line for line in rendered_lines if line.strip() not in source_lines]
            item[field] = "\n".join(kept).strip()
            if not item[field] and item.get("type") != "section":
                continue
            if item.get("type") == "section" and not item[field] and not compact_text(item.get("title")):
                continue
        item.pop("source_lines", None)
        result.append(item)
    return result


CASE_LEAD_RE = re.compile(
    r"^\s*(?P<label>一句话价值|作品价值|核心价值)\s*[：:]\s*(?P<value>.+?)\s*$"
)
CASE_QUOTE_RE = re.compile(
    r"^\s*(?P<label>为什么值得看|可复用经验|案例价值|核心价值)\s*[：:]\s*(?P<value>.+?)\s*$"
)


def _case_showcase_field_pair(
    source_lines: Sequence[str],
    rendered_lines: Sequence[str],
    pattern: re.Pattern[str],
) -> Optional[Tuple[str, str, str, str]]:
    """Return (source, rendered, label, value) for a source-backed case field."""
    for source, rendered in zip(source_lines, rendered_lines):
        match = pattern.match(str(rendered or ""))
        if not match:
            continue
        value = compact_text(match.group("value"))
        if value:
            return str(source), str(rendered), match.group("label"), value
    return None


def _promote_case_showcase_fields(
    blocks: List[Dict[str, Any]],
    source_lines: Sequence[str],
    rendered_lines: Sequence[str],
    transformations: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Optional[Tuple[str, str, str, str]]]:
    """Promote case value/quote lines before folding and scene validation."""
    lead_pair = _case_showcase_field_pair(source_lines, rendered_lines, CASE_LEAD_RE)
    quote_pair = _case_showcase_field_pair(source_lines, rendered_lines, CASE_QUOTE_RE)
    retained = blocks
    if lead_pair:
        retained = _remove_source_lines(retained, {lead_pair[1]})
        transformations.append({
            "kind": "case_lead_extraction",
            "source": lead_pair[0],
            "output": lead_pair[3],
            "reason": "case-showcase 的一句话价值进入首屏导语；只做结构提升，不改写事实",
        })
    if quote_pair:
        retained = _remove_source_lines(retained, {quote_pair[1]})
        retained.append({
            "type": "quote",
            "eyebrow": "案例价值",
            "title": quote_pair[2],
            "text": quote_pair[3],
            "emphasis": "heading",
            "source_text": quote_pair[0],
            "source_lines": [quote_pair[0]],
        })
        transformations.append({
            "kind": "case_quote_extraction",
            "source": quote_pair[0],
            "output": "native quote block",
            "reason": "case-showcase 的价值收束保持首屏可见，避免被长文折叠",
        })
    return retained, lead_pair


def enforce_text_surface_policy(
    blocks: List[Dict[str, Any]],
    decisions: List[Dict[str, Any]],
    *,
    enabled: bool = True,
) -> List[Dict[str, Any]]:
    """Put visible prose into editable highlight surfaces.

    The previous default only highlighted a few semantic headings.  That left
    ordinary case sections and the lead paragraph as naked Markdown below the
    hero image.  This pass keeps facts/timelines/charts/actions as their own
    structured components, while converting prose-bearing text/sections into
    the same native surface.  It changes presentation metadata only; the
    original source text remains unchanged in ``source_text`` and
    ``analysis.source_text``.
    """
    if not enabled:
        return blocks

    normalized: List[Dict[str, Any]] = []
    converted = 0
    for index, raw in enumerate(blocks):
        if not isinstance(raw, dict):
            normalized.append(raw)
            continue
        block = dict(raw)
        kind = str(block.get("type", block.get("kind", ""))).lower()

        if kind in {"text", "markdown", "div"}:
            content = block.get("content", block.get("text", ""))
            content_text = body_text(content).strip()
            if not content_text:
                continue
            label, body = split_text_label(content_text)
            promoted: Dict[str, Any] = {
                "type": "highlight",
                "content": body if label else content_text,
                "source_text": block.get("source_text", content_text),
                "tone": text_surface_tone(label, role="lead" if index == 0 else "module"),
                "text_size": block.get("text_size", "normal_v2"),
                "text_surface_role": "lead" if index == 0 else "module",
                "title_prefix": HIERARCHY_TITLE_PREFIX,
                "item_prefix": HIERARCHY_ITEM_PREFIX,
            }
            if label:
                promoted["title"] = label
            if block.get("element_id") or block.get("id"):
                promoted["element_id"] = block.get("element_id", block.get("id"))
            normalized.append(promoted)
            converted += 1
            continue

        if kind == "section":
            body = body_text(block.get("body", block.get("content", ""))).strip()
            title = compact_text(block.get("title"))
            if body:
                block["highlight"] = True
                block.setdefault("tone", text_surface_tone(title))
                block.setdefault("text_surface_role", "module")
                block.setdefault("title_prefix", HIERARCHY_TITLE_PREFIX)
                block.setdefault("item_prefix", HIERARCHY_ITEM_PREFIX)
                normalized.append(block)
                converted += 1
                continue

        if kind == "highlight":
            block.setdefault("title_prefix", HIERARCHY_TITLE_PREFIX)
            block.setdefault("item_prefix", HIERARCHY_ITEM_PREFIX)
            normalized.append(block)
            continue

        normalized.append(block)

    if converted:
        decisions.append({
            "decision": "applied",
            "component": "highlight_text_surfaces",
            "reason": "摘要与文字模块统一使用原生高亮块；标题以横杠分层，正文项以项目符号分组",
            "policy": TEXT_SURFACE_POLICY,
            "converted_blocks": converted,
        })
    return normalized


def apply_design_plan(
    blocks: List[Dict[str, Any]], lines: Sequence[str], design: Dict[str, Any], *, emoji_mode: str = "semantic"
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Materialize selected planner choices and preserve rejected source text."""
    result = list(blocks)
    decisions: List[Dict[str, Any]] = []
    strategies = [item for item in design.get("component_strategy", []) if isinstance(item, dict)]
    selection = {str(item.get("component")): bool(item.get("selected", True)) for item in strategies}

    def enabled(component: str) -> bool:
        return selection.get(component, True)

    for item in strategies:
        if not item.get("selected", True):
            item["status"] = "rejected"
            decisions.append({"decision": "rejected", "component": item.get("component"), "reason": item.get("reason"), "priority": item.get("priority")})

    normalized: List[Dict[str, Any]] = []
    for block in result:
        kind = block.get("type")
        if kind in {"div", "highlight"} and block.get("attention") == "alert" and not enabled("status_tag"):
            normalized.append({"type": "text", "content": block.get("content", block.get("text", ""))})
            continue
        if kind == "timeline" and not enabled("timeline"):
            restored = []
            for item in block.get("items", []):
                source_lines = item.get("source_lines") if isinstance(item, dict) else None
                if isinstance(source_lines, list) and source_lines:
                    restored.append("\n".join(str(line) for line in source_lines))
                else:
                    restored.append(item.get("source_text") or " ".join(filter(None, [item.get("date"), item.get("title"), item.get("body")])) )
            for source in restored:
                if enabled("status_tag") and re.search(r"截止|最后|请务必|必须|重要|紧急|警告", source) and len(source) <= 100:
                    marked, marker = ensure_paragraph_emoji(source, enabled=emoji_mode == "semantic")
                    normalized.append({"type": "highlight", "content": marked, "text_size": "normal_v2", "tone": "danger", "attention": "alert"})
                    if marker:
                        decisions.append({"decision": "applied", "component": "semantic_emoji", "reason": "时间线降级为提醒块后保留一个语义扫读锚点"})
                else:
                    normalized.append({"type": "text", "content": source})
            continue
        if kind == "facts" and not enabled("facts"):
            restored = [f"{item.get('label', '')}：{item.get('value', '')}" for item in block.get("items", [])]
            normalized.append({"type": "text", "content": "\n".join(restored)})
            continue
        if kind == "section" and not enabled("section"):
            restored = "\n".join(part for part in (compact_text(block.get("title")), block.get("body", "")) if part)
            normalized.append({"type": "text", "content": restored})
            continue
        normalized.append(block)
    result = normalized

    # Seed tones for source-backed semantic sections before the global
    # highlight-first pass.  The original title/body remain unchanged.
    highlight_count = sum(
        1
        for block in result
        if isinstance(block, dict)
        and (block.get("type") == "highlight" or block.get("highlight") or block.get("highlighted"))
    )
    if enabled("highlight"):
        for block in result:
            if not isinstance(block, dict) or block.get("type") != "section":
                continue
            title = compact_text(block.get("title"))
            body = compact_text(block.get("body"))
            if (
                not title
                or not body
                or len(body) > 260
                or not HIGHLIGHT_SECTION_RE.search(title)
                or highlight_count >= 3
            ):
                continue
            block["highlight"] = True
            block["tone"] = "brand" if not re.search(r"注意|提醒|风险", title) else "warning"
            highlight_count += 1
            decisions.append({
                "decision": "applied",
                "component": "highlight",
                "reason": f"高亮“{title}”区块以建立首屏层级；正文仍保持原文",
            })

    # The current default is intentionally stronger than the historical
    # selective-highlight rule: every visible prose module below the hero
    # gets an editable surface, while metrics/timelines/charts/actions keep
    # their specialized structured components.
    # This is a global readability contract, not an optional decoration
    # toggle: every visible prose module must land on an editable native
    # surface.  Metrics, timelines, charts and actions remain specialized.
    result = enforce_text_surface_policy(result, decisions, enabled=True)

    table_rows: List[List[str]] = []
    table_sources: set[str] = set()
    for line in lines:
        delimiter = "|" if line.count("|") >= 2 else "\t" if line.count("\t") >= 2 else None
        if delimiter:
            cells = [cell.strip() for cell in line.strip().strip("|").split(delimiter)]
            if len(cells) >= 2:
                table_rows.append(cells)
                table_sources.add(line.strip())
    if enabled("table") and len(table_rows) >= 2 and len({len(row) for row in table_rows}) == 1:
        header, rows = table_rows[0], table_rows[1:]
        result = _remove_source_lines(result, table_sources)
        result.append({"type": "table", "columns": header, "rows": rows})
        decisions.append({"decision": "applied", "component": "table", "reason": "结构一致的分隔行已可靠解析；原文单元格未改写"})

    metric_records = extract_metrics("\n".join(lines))
    metric_rows: List[Dict[str, Any]] = [
        {
            "label": item["label"],
            "value": item["display"],
            "numeric_value": item["value"],
            "unit_family": item["unit_family"],
            "source_text": item["source_text"],
            "source_lines": [item["source_text"]],
        }
        for item in metric_records
    ]
    metric_sources = {str(item["source_text"]).strip() for item in metric_records}
    if enabled("metrics") and metric_rows:
        if emoji_mode == "semantic" and not any(has_emoji(str(item.get("label") or "")) for item in metric_rows):
            # Metric-only cards have no paragraph/fact heading where the
            # semantic emoji budget can naturally attach. Put one restrained
            # chart marker on the first metric label so the native Card still
            # gets a real scan anchor instead of failing the emoji gate.
            metric_rows[0]["label"] = f"📊 {metric_rows[0]['label']}"
            decisions.append({
                "kind": "metrics_emoji",
                "source": metric_rows[0]["source_text"],
                "output": metric_rows[0]["label"],
                "emoji": "📊",
                "reason": "指标组缺少段落标题；在首个指标上保留一个语义图表锚点",
            })
        result = _remove_source_lines(result, metric_sources)
        result.insert(0, {"type": "metrics", "items": metric_rows[:4]})
        decisions.append({"decision": "applied", "component": "metrics", "reason": "来源数值已提升为事实卡；缩短/提升等前缀与单位保持原文"})
        chart = build_chart_plan("\n".join(lines), metric_records)
        chart_block = chart_block_from_plan(chart)
        if chart_block and enabled("chart"):
            result.insert(1, chart_block)
            decisions.append({"decision": "applied", "component": "chart", "reason": "至少两个同口径来源数值已路由为原生 CardKit 图表；混合单位未合并"})
        if len(metric_rows) > 4:
            decisions.append({"decision": "deferred", "component": "extra_metrics", "reason": "首屏只保留 4 个关键指标；其余数值保留在 source.txt 及 visual-spec.json"})

    fold = design.get("fold_strategy") if isinstance(design.get("fold_strategy"), dict) else {}
    if enabled("collapsible_panel") and fold.get("use_collapsible_panel") and len(result) > 2:
        def salience(block: Dict[str, Any]) -> int:
            kind = block.get("type")
            text = compact_text(block)
            if block.get("attention") == "alert" or re.search(r"截止|警告|紧急|务必|当前阶段", text):
                return 0
            if kind in {"facts", "metrics"}:
                return 1
            if kind == "quote":
                return 1
            if kind == "timeline":
                return 2
            return 4

        ranked = sorted(enumerate(result), key=lambda pair: (salience(pair[1]), pair[0]))
        visible_indexes = {index for index, block in ranked if salience(block) <= 2}
        if not visible_indexes:
            first_ordinary = next((index for index, _block in enumerate(result)), None)
            if first_ordinary is not None:
                visible_indexes.add(first_ordinary)
        visible = [block for index, block in enumerate(result) if index in visible_indexes]
        supporting = [block for index, block in enumerate(result) if index not in visible_indexes]
        if supporting:
            summary = design.get("summary_extraction") if isinstance(design.get("summary_extraction"), dict) else {}
            mode = str(summary.get("mode") or design.get("content_mode") or "").strip()
            fold_title = {
                "meeting_summary": "展开会议/沟通详情",
                "work_report": "展开工作明细",
                "long_summary": "展开补充信息",
            }.get(mode, "展开补充信息")
            result = visible + [{
                "type": "collapse", "title": fold_title, "blocks": supporting
            }]
            decisions.append({"decision": "applied", "component": "collapsible_panel", "reason": "截止/警告、当前阶段、核心指标和时间线优先首屏；普通长正文后置折叠，分组内保持原始顺序"})
    return result, decisions


def _compact_display_text(value: Any, *, max_chars: int = 120, max_lines: int = 2) -> str:
    """Select source-backed clauses for the visible card without paraphrasing."""
    from text_quality import concise
    return concise(value, max_chars, max_lines)


def _visible_block_text_chars(blocks: Sequence[Dict[str, Any]]) -> int:
    display_fields = {"title", "body", "content", "text", "label", "value", "date", "eyebrow"}

    def walk(value: Any, key: Optional[str] = None) -> int:
        if isinstance(value, str):
            return len(value) if key in display_fields else 0
        if isinstance(value, list):
            return sum(walk(item, key) for item in value)
        if isinstance(value, dict):
            return sum(
                walk(item, str(item_key))
                for item_key, item in value.items()
                if item_key not in {"source_text", "source_lines", "chart_spec"}
            )
        return 0

    return walk(list(blocks))


def compact_visible_blocks(
    blocks: Sequence[Dict[str, Any]],
    source_text: str,
    transformations: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Keep a mobile card concise while preserving the full canonical source."""
    original = [block for block in blocks if isinstance(block, dict)]
    original_chars = _visible_block_text_chars(original)
    needs_compaction = (len(source_text.strip()) > 280 or len(original) > 6 or original_chars > 500
                        or any(_visible_block_text_chars([b]) > 220 for b in original))
    if not needs_compaction:
        return list(original), {
            "applied": False,
            "visible_block_count": len(original),
            "visible_text_chars": original_chars,
            "full_source": "analysis.source_text and <name>.source.txt",
        }

    # A collapse containing the entire source only hides the wall of text; it
    # does not solve it.  Expand its children into the candidate stream, then
    # select a compact visible subset.
    candidates: List[Dict[str, Any]] = []
    for block in original:
        if block.get("type") in {"collapse", "collapsible_panel"}:
            candidates.extend(item for item in block.get("blocks", []) if isinstance(item, dict))
        else:
            candidates.append(block)

    # Prose is promoted to native highlight surfaces before compaction.  Keep
    # enough surfaces for a short case story (lead + background + method +
    # result + value), while still applying the visible-text budget below.
    quotas = {"text": 1, "div": 1, "highlight": 5, "section": 3, "quote": 1, "timeline": 1, "facts": 1, "metrics": 1, "chart": 1, "buttons": 1}
    used = {key: 0 for key in quotas}
    compacted: List[Dict[str, Any]] = []
    omitted: List[Dict[str, Any]] = []
    seen_copy: set[str] = set()
    for block in candidates:
        kind = str(block.get("type") or "text")
        bucket = "buttons" if kind in {"button", "buttons"} else kind
        if bucket not in quotas:
            # Compaction must not delete images, galleries, forms or other functional blocks.
            compacted.append(dict(block))
            continue
        if used[bucket] >= quotas[bucket]:
            omitted.append(block)
            continue
        item = dict(block)
        if kind in {"text", "div", "highlight"}:
            field = "content" if "content" in item else "text"
            item[field] = _compact_display_text(item.get(field), max_chars=110, max_lines=1)
        elif kind == "section":
            item["body"] = _compact_display_text(item.get("body", item.get("content", "")), max_chars=60, max_lines=2)
        elif kind == "quote":
            item["text"] = _compact_display_text(item.get("text", item.get("content", "")), max_chars=120, max_lines=1)
        elif kind in {"facts", "metrics"}:
            item["items"] = list(item.get("items", []))[:4]
        elif kind == "timeline":
            timeline_items: List[Dict[str, Any]] = []
            for row in list(item.get("items", []))[:4]:
                if not isinstance(row, dict):
                    continue
                compact_row = dict(row)
                compact_row["body"] = _compact_display_text(row.get("body", row.get("content", "")), max_chars=84, max_lines=2)
                timeline_items.append(compact_row)
            item["items"] = timeline_items
        if kind in {"text", "div", "highlight", "section"}:
            copy_key = str(item.get("body") or item.get("content") or item.get("text") or "").strip()
            if copy_key and copy_key in seen_copy:
                omitted.append(block)
                continue
            seen_copy.add(copy_key)
        compacted.append(item)
        used[bucket] += 1

    # Preserve supplied action positions; the source-backed coordination pass
    # binds auto-generated actions to their exact module, leaving global CTAs last.
    visible_chars = _visible_block_text_chars(compacted)
    transformations.append({
        "kind": "visible_card_compaction",
        "source": f"{len(source_text)} characters / {len(original)} blocks",
        "output": f"{visible_chars} visible characters / {len(compacted)} blocks",
        "reason": "移动端默认只保留核心摘要、3–5 个关键点、指标/图表和真实 CTA；完整原文保留在 source.txt",
    })
    return compacted, {
        "applied": True,
        "original_block_count": len(original),
        "visible_block_count": len(compacted),
        "omitted_block_count": len(omitted),
        "original_text_chars": original_chars,
        "visible_text_chars": visible_chars,
        "full_source": "analysis.source_text and <name>.source.txt",
        "full_text_button_policy": "only a real source URL may open the full document",
    }


def _block_types(blocks: Any) -> set[str]:
    found: set[str] = set()
    if not isinstance(blocks, list):
        return found
    for block in blocks:
        if not isinstance(block, dict):
            continue
        kind = str(block.get("type", block.get("kind", ""))).lower()
        if kind:
            found.add(kind)
        found.update(_block_types(block.get("blocks", block.get("elements", []))))
    return found


def close_design_decisions(spec: Dict[str, Any], design: Dict[str, Any], decisions: List[Dict[str, Any]]) -> None:
    """Ensure every selected recommendation is materialized or explicitly degraded."""
    types = _block_types(spec.get("blocks"))
    aliases = {
        "status_tag": bool(any(isinstance(block, dict) and block.get("attention") == "alert" for block in spec.get("blocks", []))),
        "highlight": bool(any(
            isinstance(block, dict)
            and (block.get("type") == "highlight" or block.get("highlight") or block.get("highlighted"))
            for block in spec.get("blocks", [])
        )),
        "timeline": "timeline" in types,
        "facts": bool(types & {"facts", "metrics"}),
        "metrics": bool(types & {"facts", "metrics"}),
        "table": "table" in types,
        "chart": "chart" in types,
        "section": bool(types & {"section", "text", "markdown", "div"}),
        "collapsible_panel": bool(types & {"collapse", "collapsible_panel"}),
        "buttons": bool(types & {"button", "buttons"}),
        # A planned hero is selected before Seedream 5.0 Pro/upload.  Testing only for
        # img_key here made a valid scene look degraded before its asset was
        # available.
        "hero": isinstance(spec.get("hero"), dict) and bool(spec.get("hero")),
        "image_combination": bool(types & {"image_combination", "image_group", "gallery"}),
        "media_switcher": "media_switcher" in types,
    }
    for item in design.get("component_strategy", []):
        if not isinstance(item, dict) or not item.get("selected", True):
            continue
        component = str(item.get("component", ""))
        if component == "hero" and isinstance(spec.get("hero"), dict):
            if spec.get("hero", {}).get("img_key"):
                item["status"] = "applied"
                if not any(log.get("decision") == "applied" and log.get("component") == component for log in decisions):
                    decisions.append({"decision": "applied", "component": component, "reason": item.get("reason")})
            else:
                item["status"] = "needs_assets"
                decisions.append({
                    "decision": "pending",
                    "component": component,
                    "reason": f"{item.get('reason', '')}；结构已应用，等待真实 hero img_key",
                })
            continue
        if aliases.get(component, False):
            item["status"] = "applied"
            if not any(log.get("decision") == "applied" and log.get("component") == component for log in decisions):
                decisions.append({"decision": "applied", "component": component, "reason": item.get("reason")})
            continue
        media_policy = design.get("media_policy") if isinstance(design.get("media_policy"), dict) else {}
        if component in {"image_combination", "media_switcher"} and bool(media_policy.get("need_gallery" if component == "image_combination" else "need_switcher")):
            item["status"] = "needs_assets"
            decisions.append({
                "decision": "pending",
                "component": component,
                "reason": f"{item.get('reason', '')}；已记录媒体需求，待提供每张图片的真实 img_key 后编译",
            })
            continue
        item["selected"] = False
        item["status"] = "degraded"
        reason = f"{item.get('reason', '')}；未从原文可靠解析出可用数据，已显式降级"
        item["reason"] = reason
        decisions.append({"decision": "degraded", "component": component, "reason": reason})
        if component == "collapsible_panel":
            design["fold_strategy"] = {**design.get("fold_strategy", {}), "mode": "none", "use_collapsible_panel": False, "reason": "可折叠辅助块不足，保留单页"}
        if component == "timeline" and spec.get("scene") == "activity-timeline":
            spec["scene"] = None
            spec["type"] = "custom"
            design["scene"] = "custom"
            decisions.append({"decision": "degraded", "component": "scene", "reason": "activity-timeline 缺少可解析 timeline，降级为 custom，避免场景契约失败"})

    scene_id = spec.get("scene")
    if not scene_id:
        return
    scene = next((item for item in json.loads(SCENE_REGISTRY_PATH.read_text(encoding="utf-8")).get("scenes", []) if item.get("id") == scene_id), None)
    if not isinstance(scene, dict):
        return
    aliases = {
        "facts": {"facts", "metrics"}, "sections": {"section", "markdown", "text", "div"},
        "timeline": {"timeline"}, "buttons": {"buttons", "button"}, "quote": {"quote"},
    }
    types = _block_types(spec.get("blocks"))
    missing: List[str] = []
    for field in scene.get("required_fields", []):
        value = spec.get(field)
        present = bool(value.strip()) if isinstance(value, str) else bool(value)
        if not present and field in aliases:
            present = bool(types & aliases[field])
        if not present:
            missing.append(field)
    if missing:
        spec["scene"] = None
        spec["type"] = "custom"
        design["baseline_scene"] = scene_id
        design["scene"] = "custom"
        decisions.append({
            "decision": "degraded",
            "component": "scene",
            "reason": f"{scene_id} 缺少场景契约字段 {', '.join(missing)}，已降级为 custom",
        })


def build_auto_spec(
    text: str,
    *,
    requested_type: Optional[str] = None,
    requested_scene: Optional[str] = None,
    requested_preset: Optional[str] = None,
    emoji_mode: str = "semantic",
    dedupe: str = "safe",
    link_mode: str = "button",
    planning: Optional[Mapping[str, Any]] = None,
    design_plan: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("plain text input cannot be empty")
    # ``source_text`` is the immutable audit source.  Any BOM/date/Emoji
    # cleanup below is display-only and is recorded in transformations.
    source_text = text
    raw_lines = source_text.splitlines() or [source_text]
    transformations: List[Dict[str, Any]] = []
    if emoji_mode not in {"auto", "aliases", "semantic", "off"}:
        raise ValueError("emoji_mode must be auto, aliases, semantic, or off")
    if link_mode not in LINK_MODES:
        raise ValueError("link_mode must be button or inline")
    if dedupe not in {"safe", "off"}:
        raise ValueError("dedupe must be safe or off")
    normalized_lines = list(raw_lines)
    if emoji_mode in {"auto", "aliases", "semantic"}:
        normalized_lines = [normalize_emoji_aliases(line) for line in normalized_lines]
        for source, output in zip(raw_lines, normalized_lines):
            if source != output:
                transformations.append({"kind": "emoji_alias", "source": source, "output": output})

    # Dates are canonicalized before facts and timeline rows are parsed, so a
    # shorthand such as 0809 or 8.9 is also readable when it appears inside a
    # ``截止时间：...`` fact instead of only when it is a timeline marker.
    display_lines: List[str] = []
    for source_line, line in zip(raw_lines, normalized_lines):
        display_line = line.replace("\ufeff", "")
        normalized_date_line, date_changes = normalize_dates(display_line)
        for change in date_changes:
            transformations.append({**change, "source_text": source_line})
        display_lines.append(normalized_date_line)
    normalized_lines = display_lines

    first_index = next((index for index, line in enumerate(normalized_lines) if line.strip()), None)
    if first_index is None:
        raise ValueError("plain text input cannot contain only blank lines")
    title = normalized_lines[first_index].strip()
    if title.startswith("#"):
        cleaned_title = title.lstrip("#").strip()
        transformations.append({"kind": "heading_marker", "source": title, "output": cleaned_title})
        title = cleaned_title

    content_lines = [line for index, line in enumerate(normalized_lines) if index != first_index and line.strip()]
    duplicate_candidates: List[Dict[str, Any]] = []
    seen_exact: Dict[str, int] = {}
    kept_lines: List[str] = []
    for index, line in enumerate(content_lines, start=1):
        key = compact_text(line)
        if dedupe == "safe" and key in seen_exact:
            duplicate_candidates.append({"kind": "exact_duplicate", "source_text": line, "first_occurrence": seen_exact[key], "dropped_from_render": True})
            transformations.append({"kind": "safe_exact_dedupe", "source": line})
            continue
        previous_duplicate = next(
            (previous for previous in kept_lines if high_confidence_duplicate(line, previous)),
            None,
        )
        if dedupe == "safe" and previous_duplicate is not None:
            duplicate_candidates.append({
                "kind": "high_confidence_duplicate",
                "source_text": line,
                "duplicate_of": previous_duplicate,
                "dropped_from_render": True,
            })
            transformations.append({
                "kind": "safe_high_confidence_dedupe",
                "source": line,
                "duplicate_of": previous_duplicate,
                "reason": "仅移除标点/空白或高置信度同义重复；原文仍保存在 source_text",
            })
            continue
        seen_exact[key] = index
        kept_lines.append(line)

    near_duplicate_candidates: List[Dict[str, Any]] = []
    for index, line in enumerate(kept_lines):
        for previous_index, previous in enumerate(kept_lines[:index]):
            if len(line) >= 14 and len(previous) >= 14 and _similarity(line, previous) >= 0.82:
                near_duplicate_candidates.append({"kind": "near_duplicate_review", "first": previous, "second": line, "similarity": round(_similarity(line, previous), 2)})

    plan_override = design_plan if design_plan is not None else planning
    if plan_override is not None and not isinstance(plan_override, Mapping):
        raise ValueError("planning/design_plan override must be an object")
    design = plan_card(source_text, plan_override, requested_scene=requested_scene)
    planned_scene = design.get("scene") if isinstance(design.get("scene"), str) else None
    selected_scene = requested_scene or (planned_scene if planned_scene and planned_scene != "custom" else None)
    try:
        scene_id, inferred_type, scene_transformations = infer_scene("\n".join([title] + kept_lines), selected_scene)
    except ValueError:
        # Semantic overrides may use a custom scene unknown to the lifecycle
        # registry. Keep registry keyword routing as the compatibility fallback.
        scene_id, inferred_type, scene_transformations = infer_scene("\n".join([title] + kept_lines), requested_scene)
    transformations.extend(scene_transformations)
    content_intelligence = analyze_content(source_text, scene=scene_id)
    summary_mode = classify_content(source_text)
    summary_extraction = extract_structured_sections(source_text, summary_mode["mode"])
    # A semantic override may intentionally change the visual treatment, but
    # the source-locked analysis remains the baseline unless the caller has
    # explicitly supplied a replacement field.
    design.setdefault("content_intelligence", content_intelligence)
    design.setdefault("attention_map", content_intelligence["attention_map"])
    design.setdefault("button_suggestions", content_intelligence["button_suggestions"])
    design.setdefault("media_plan", content_intelligence["media_plan"])
    design.setdefault("promotion_copy", content_intelligence["promotion_copy"])
    design.setdefault("content_mode", summary_mode["mode"])
    design.setdefault("content_mode_confidence", summary_mode["confidence"])
    design.setdefault("content_mode_reason", summary_mode["reason"])
    design.setdefault("summary_extraction", summary_extraction)
    media_design = design.setdefault("media_policy", {})
    if isinstance(media_design, dict):
        inferred_media = content_intelligence["media_plan"]
        for key in ("visual_job", "composition", "role", "source_spans", "native_text_pairing"):
            if media_design.get(key) in (None, "", []):
                media_design[key] = inferred_media.get(key)
        # These flags describe the selected carrier. The stable default asks
        # for one information visual, while an explicit no-image request wins.
        has_media_route = any(key in media_design for key in ("need_hero", "need_gallery", "need_switcher"))
        selected_visual = bool(
            media_design.get("need_hero")
            or media_design.get("need_gallery")
            or media_design.get("need_switcher")
            if has_media_route
            else inferred_media.get("information_carrier")
        )
        media_design["information_carrier"] = selected_visual
        media_design["not_decorative"] = selected_visual
        media_design.setdefault("facts_must_remain_in_text", True)
    card_type = requested_type or inferred_type or "custom"
    # Scene defaults are part of the stable visual contract.  An archetype
    # recommendation is useful for custom cards, but it must not override the
    # registered palette for an explicitly or structurally selected scene.
    scene_preset = scene_default_preset(scene_id)
    preset = requested_preset or scene_preset or design.get("recommended_preset")
    template_id = canonical_template_id(preset)
    if scene_id and preset:
        design["recommended_preset"] = preset
    template_selection = {
        "template_id": template_id,
        "mode": "explicit" if requested_preset else ("scene_default" if scene_preset else "content_auto"),
        "reason": (
            "用户显式指定模板"
            if requested_preset
            else f"场景 {scene_id} 使用注册的默认模板 {template_id}"
            if scene_preset
            else f"按内容原型 {design.get('visual_archetype') or 'general'} 自动选择模板 {template_id}"
        ),
        "explicit_template_supported": True,
        "spacing_multiplier": 1.5,
        "base_visual_language": "Apple 官网式现代主义层级纪律 + 高级信息设计材质：克制配色、舒展留白、通栏/细线分隔、透明磨砂玻璃、柔和动态模糊与低饱和渐变光晕；禁止廉价高饱和装饰和无意义卡片墙",
    }
    design["template_selection"] = template_selection
    # The first non-empty line is promoted to the Card title, but it can still
    # contain a real action URL or a markdown image. Keep it in the scan so a
    # title such as “报名入口: URL” is not silently discarded.
    source_lines_for_links = [title, *kept_lines]
    media_sources = extract_media_sources(source_lines_for_links)
    media_urls = {item["source"] for item in media_sources}
    raw_button_suggestions = content_intelligence.get("button_suggestions", [])
    button_urls = {
        str(item.get("url"))
        for item in raw_button_suggestions
        if isinstance(item, dict) and item.get("button_eligible") and item.get("selected") and item.get("url")
    }
    button_labels = {
        str(item.get("url")): str(item.get("label") or "").strip()
        for item in raw_button_suggestions
        if isinstance(item, dict) and item.get("button_eligible") and item.get("selected") and item.get("url") and str(item.get("label") or "").strip()
    }
    all_links, link_transformations = extract_urls(
        source_lines_for_links,
        excluded_urls=media_urls,
        allowed_urls=button_urls if link_mode == "button" else None,
        button_labels=button_labels,
    )
    transformations.extend(link_transformations)
    selected_components = {
        str(item.get("component")): bool(item.get("selected", True))
        for item in design.get("component_strategy", []) if isinstance(item, dict)
    }
    action_styles = {str(item.get("url")): item.get("button_kind") for item in raw_button_suggestions if isinstance(item, dict) and item.get("button_kind")}
    for link in all_links:
        if link["url"] in action_styles:
            link["style"] = action_styles[link["url"]]
    buttons_enabled = selected_components.get("buttons", True)
    effective_link_mode = link_mode
    links = all_links if link_mode == "button" and buttons_enabled else []
    if link_mode == "button" and not buttons_enabled:
        effective_link_mode = "inline"
    rendered_title = route_link_text(
        [title],
        transformations,
        effective_link_mode,
        media_urls=media_urls,
        button_urls=button_urls if effective_link_mode == "button" else set(),
    )[0]
    title = rendered_title or title
    rendered_lines = route_link_text(
        kept_lines,
        transformations,
        effective_link_mode,
        media_urls=media_urls,
        button_urls=button_urls if effective_link_mode == "button" else set(),
    )
    blocks = build_blocks(rendered_lines, transformations, emoji_mode=emoji_mode, scene=scene_id)
    case_lead_pair: Optional[Tuple[str, str, str, str]] = None
    if scene_id == "case-showcase":
        # Materialize the case-specific value/quote fields before the generic
        # long-summary fold runs; otherwise the story route loses its quote
        # contract and silently falls back to ``custom``.
        blocks, case_lead_pair = _promote_case_showcase_fields(
            blocks,
            kept_lines,
            rendered_lines,
            transformations,
        )
    blocks, decision_log = apply_design_plan(blocks, rendered_lines, design, emoji_mode=emoji_mode)
    eligible_button_count = sum(
        1 for item in raw_button_suggestions
        if isinstance(item, dict) and item.get("button_eligible")
    )
    if link_mode == "button" and eligible_button_count > 2:
        decision_log.append({"decision": "rejected", "component": "buttons", "reason": "明确动作超过 2 个；只保留一个主按钮和最多一个次按钮，其余 URL 保留在原文语境中"})
    if link_mode == "button" and not button_urls and any(URL_RE.search(line) for line in source_lines_for_links):
        decision_log.append({"decision": "deferred", "component": "buttons", "reason": "URL 缺少明确动作语义或只有参考属性；保留行内 URL，不强行生成按钮"})

    media_hints = "\n".join(source_lines_for_links)
    image_markers = [match.groupdict() for line in source_lines_for_links for match in IMAGE_MARKER_RE.finditer(line)]
    media_policy = design.get("media_policy") if isinstance(design.get("media_policy"), dict) else {}
    wants_switcher = bool(media_policy.get("need_switcher")) or bool(MEDIA_SWITCH_RE.search(media_hints))
    wants_media = bool(image_markers or media_sources or media_policy.get("need_hero") or media_policy.get("need_gallery") or wants_switcher)
    wants_gif = bool(media_sources and any(item.get("kind") == "gif" for item in media_sources)) or bool(re.search(r"动图|GIF|动画", media_hints, re.I)) or media_policy.get("motion") == "gif"
    planned_media_request = bool(
        media_policy.get("need_hero")
        or media_policy.get("need_gallery")
        or wants_switcher
    )
    content_allocation = build_information_allocation(
        source_text,
        scene=scene_id,
        title=title,
        blocks=blocks,
        button_suggestions=raw_button_suggestions,
        explicit_media=bool(image_markers or media_sources or planned_media_request),
        supplied_media=bool(media_sources),
        force_no_image=not wants_media and not media_sources,
    )
    design["information_allocation"] = content_allocation

# An explicitly supplied markdown image is a real-image asset. A
# 豆包工作-default hero is an AI asset and will later require an
# Seedream 5.0 Pro-class provenance manifest. The distinction is metadata here;
    # remote delivery still requires a real Feishu img_key.
    image_source = "real_image" if media_sources else (
        "ai_generated" if wants_media and not media_policy.get("need_gallery") else "none"
    )
    configured_mode = str(media_policy.get("image_generation_mode") or "").strip()
    selected_image_mode = configured_mode or _default_image_mode()
    if selected_image_mode not in SUPPORTED_IMAGE_MODES:
        raise ValueError(
            f"image_generation_mode must be one of {', '.join(SUPPORTED_IMAGE_MODES)}; remove the legacy image-generation mode"
        )
    selected_mode_config = _image_mode_config(selected_image_mode)
    runtime_model, runtime_model_label = _runtime_model()
    image_roles: List[str] = (
        [str(item) for item in selected_mode_config.get("roles", []) if str(item).strip()]
        if image_source != "none"
        else []
    )
    if isinstance(media_policy, dict):
        media_policy["image_source"] = image_source
        media_policy["image_roles"] = image_roles
        media_policy["generation_family"] = "seedream-class" if image_source == "ai_generated" else None
        media_policy["generation_tool"] = "doubao.image_gen" if image_source == "ai_generated" else None
        media_policy["generation_model"] = runtime_model if image_source == "ai_generated" else None
        media_policy["generation_model_label"] = runtime_model_label if image_source == "ai_generated" else None
        media_policy["image_generation_mode"] = selected_image_mode
        media_policy["information_allocation"] = content_allocation
        media_policy["source_spans"] = [
            item.get("source_text")
            for item in content_allocation.get("image", {}).get("include", [])
            if isinstance(item, dict) and item.get("source_text")
        ]
        if image_source == "real_image":
            media_policy["real_image_policy"] = "preserve supplied pixels and source metadata; run media_assets.py before upload"
        if not selected_visual and not media_sources:
            media_policy["visual_job"] = "用户明确要求无图；原生 Card 保留精简摘要和真实行动，完整事实仍在 source.txt"
            media_policy["composition"] = None
            media_policy["role"] = "native_card"
            media_policy["source_spans"] = []

    first_date = next((find_date_info(line) for line in kept_lines if find_date_info(line)), None)
    timeline_focus = design.get("focus_mode") == "timeline-first" or (
        scene_id == "activity-timeline" and len(content_intelligence.get("date_candidates", [])) >= 2
    )
    media_contract = design.get("media_policy") if isinstance(design.get("media_policy"), dict) else {}
    spec: Dict[str, Any] = {
        "type": card_type,
        "title": title,
        "scene": scene_id,
        "preset": preset,
        "template_id": template_id,
        "template_selection": template_selection,
        "route_contract": {
            "profile": "stable-v1",
            "precedence": "explicit_scene > source_structure > specific_keywords > custom",
            "scene_default_preset": scene_preset,
            "requested_scene": requested_scene,
            "template_selection": template_selection,
        },
        "content_mode": summary_mode["mode"],
        "content_mode_confidence": summary_mode["confidence"],
        "summary_structure": summary_extraction,
        "suppress_generated_labels": True,
        "auto_emphasis": True,
        "text_surface_policy": TEXT_SURFACE_POLICY,
        "hierarchy_markers": {
            "title_prefix": HIERARCHY_TITLE_PREFIX,
            "item_prefix": HIERARCHY_ITEM_PREFIX,
            "separator": "／",
        },
        "timeline_focus": timeline_focus,
        "timeline_first": timeline_focus,
        "emoji_mode": emoji_mode,
        "blocks": blocks,
        "information_allocation": content_allocation,
        "visual_contract": {
            "role": media_contract.get("role", "information_anchor"),
            "not_decorative": bool(media_contract.get("not_decorative", False)),
            "image_source": image_source,
            "image_roles": image_roles,
            "job": media_contract.get("visual_job"),
            "composition": media_contract.get("composition"),
            "source_spans": media_contract.get("source_spans", []),
            "pairing": media_contract.get("native_text_pairing"),
            "text_in_image": "none",
            "information_allocation": content_allocation,
            "native_text_is_complete": False,
            "native_text_policy": "concise summary + 3–5 key points + source-backed metrics/chart + real CTA",
        },
        "prompt_routing": design.get("prompt_routing", {}),
        "analysis": {
            "mode": "auto",
            "policy": "faithful-source-first",
            "source_locked": True,
            "source_text": source_text,
            "source_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
            "source_line_count": len(raw_lines),
            "rendered_line_count": len(kept_lines) + 1,
            "transformations": transformations,
            "duplicate_candidates": duplicate_candidates,
            "near_duplicate_candidates": near_duplicate_candidates,
            "detected_urls": [item["url"] for item in all_links],
            "link_mode": effective_link_mode,
            "requested_link_mode": link_mode,
            "design_plan": design,
            "content_intelligence": content_intelligence,
            "content_policy": content_intelligence["rewrite_policy"],
            "attention_map": content_intelligence["attention_map"],
            "button_suggestions": content_intelligence["button_suggestions"],
            "information_allocation": content_allocation,
            "promotion_copy": content_intelligence["promotion_copy"],
            "summary_extraction": summary_extraction,
            "decision_log": decision_log,
            "media_requests": media_sources or ([
                {
                    "kind": "gif" if wants_gif else "image",
                    "mode": "switcher" if wants_switcher else ("animated" if wants_gif else "static"),
                    "source_markers": image_markers,
                    "reason": "source text requests visual media" if image_markers or wants_gif else "豆包工作 image is an information carrier, not decoration",
                    "requires_application_bot": wants_switcher,
                    "static_first_frame_required": wants_gif,
                }
            ] if wants_media else []),
            "review_before_send": bool(duplicate_candidates or near_duplicate_candidates or links or wants_media),
        },
    }
    spec["media_contract"] = {
        "mode": "switcher" if wants_switcher else ("gif" if wants_gif else ("gallery" if media_policy.get("need_gallery") else "static")),
        "image_source": image_source,
        "image_roles": image_roles,
        "information_allocation": content_allocation,
        "generation_family": "seedream-class" if image_source == "ai_generated" else None,
        "generation_tool": "doubao.image_gen" if image_source == "ai_generated" else None,
        "generation_model": runtime_model if image_source == "ai_generated" else None,
        "generation_model_label": runtime_model_label if image_source == "ai_generated" else None,
        "requires_application_bot": wants_switcher,
        "static_first_frame_required": wants_gif,
        "asset_manifest_command": "python3 scripts/media_assets.py --input <asset> --output <bundle>/<name>.media-manifest.json",
        "fallback": "首张静态图必须独立可读；动图和切换状态都不能成为唯一事实载体",
    }
    if first_date and first_date.get("display"):
        spec["date_label"] = first_date["display"]
    if scene_id in {"prelaunch-promo", "case-showcase"}:
        lead_pair = case_lead_pair or next((
            (original, rendered, "", compact_text(rendered))
            for original, rendered in zip(kept_lines, rendered_lines)
            if not _fact(original) and not _is_heading(original) and not URL_RE.fullmatch(original.strip()) and compact_text(original)
        ), None)
        if lead_pair:
            lead_source, lead_rendered, lead_label, lead_value = lead_pair
            spec["lead"] = lead_value
            if lead_label:
                spec["lead_label"] = lead_label
                spec["lead_source_text"] = lead_source
            # In inline mode the source line remains in blocks so callers can
            # inspect the original URL.  In button mode remove it from the
            # body because the same source line is represented by the CTA.
            if effective_link_mode == "button" and not case_lead_pair and URL_RE.search(lead_source):
                spec["blocks"] = _remove_source_lines(spec["blocks"], {lead_source})
            if not case_lead_pair:
                transformations.append({"kind": "lead_extraction", "source": lead_source, "output": lead_rendered, "reason": "场景契约需要导语；只做结构提升，不改事实"})
    if links:
        spec["blocks"].append({"type": "buttons", "items": links, "auto_generated": True})
    if wants_media and not media_policy.get("need_gallery") and selected_components.get("hero", True):
        spec["hero"] = {
            "alt": f"{title}信息视觉",
            "asset_kind": "gif" if wants_gif else "image",
            "motion": "slow gold-node breathing; static first frame must remain complete" if wants_gif else "static editorial hero",
            "role": media_policy.get("role") or "information_anchor",
            "information_carrier": True,
            "image_source": image_source,
            "image_roles": image_roles,
        }
        if image_source == "ai_generated":
            spec["hero"]["generation_family"] = "seedream-class"
            spec["hero"]["generation_tool"] = "doubao.image_gen"
            spec["hero"]["generation_model"] = runtime_model
            spec["hero"]["generation_model_label"] = runtime_model_label
            spec["hero"]["generation_provenance"] = "hero-generation.json"
        elif image_source == "real_image":
            spec["hero"]["real_image_policy"] = "preserve supplied pixels; pair with native facts and source metadata"
        if media_policy.get("prompt_brief"):
            spec["hero"]["prompt"] = media_policy["prompt_brief"]
        if media_sources and "hero" in spec:
            spec["hero"]["source_markers"] = media_sources
            preferred_source = next((item for item in media_sources if wants_gif and item.get("kind") == "gif"), media_sources[0])
            spec["hero"]["source_url"] = preferred_source.get("source")

    visual_spec = build_visual_spec(source_text, title=title, no_image=not wants_media)
    spec["visual_spec"] = visual_spec
    compacted_blocks, visible_content = compact_visible_blocks(spec["blocks"], source_text, transformations)
    spec["blocks"] = compacted_blocks
    analysis = spec["analysis"]
    analysis["visible_content"] = visible_content
    analysis["visual_spec"] = visual_spec

    # Recompute after link routing, quote/lead promotion inputs, and block
    # materialization so the final allocation explains the actual Card.
    content_allocation = build_information_allocation(
        source_text,
        scene=scene_id,
        title=title,
        blocks=spec["blocks"],
        button_suggestions=raw_button_suggestions,
        explicit_media=bool(image_markers or media_sources or planned_media_request),
        supplied_media=bool(media_sources),
        force_no_image=not wants_media and not media_sources,
    )
    design["information_allocation"] = content_allocation
    spec["information_allocation"] = content_allocation
    spec["visual_contract"]["information_allocation"] = content_allocation
    if isinstance(media_policy, dict):
        media_policy["information_allocation"] = content_allocation

    image_text_checklist = build_image_text_checklist(spec["blocks"], title, allocation=content_allocation)
    configured_image_mode = str(media_policy.get("image_generation_mode") or "").strip()
    effective_image_mode = configured_image_mode or _default_image_mode()
    if effective_image_mode not in SUPPORTED_IMAGE_MODES:
        raise ValueError(
            f"image_generation_mode must be one of {', '.join(SUPPORTED_IMAGE_MODES)}; remove the legacy image-generation mode"
        )
    selected_mode_config = _image_mode_config(effective_image_mode)
    image_text_mode = (
        str(selected_mode_config.get("text_policy") or DIRECT_SEEDREAM_TEXT_MODE)
        if isinstance(spec.get("hero"), dict) and image_text_checklist
        else "none"
    )
    image_text_layout = effective_image_mode if image_text_mode != "none" else None
    visual_contract = spec.get("visual_contract")
    if isinstance(visual_contract, dict):
        visual_contract["text_in_image"] = image_text_mode
        visual_contract["functional_text"] = image_text_checklist if image_text_mode != "none" else []
        visual_contract["functional_text_source_locked"] = image_text_mode != "none"
        visual_contract["image_text_layout"] = image_text_layout
        visual_contract["image_text_scope"] = (
            "Seedream 5.0 Pro directly renders only the source-backed text selected by information_allocation.image.include; native Card keeps a concise editable summary and key facts while source.txt keeps the complete source; no post-processing text layer"
            if image_text_mode != "none"
            else None
        )
        visual_contract["native_text_scope"] = content_allocation.get("native_card")
    if isinstance(media_policy, dict):
        media_policy["text_in_image"] = image_text_mode
        media_policy["functional_text"] = image_text_checklist if image_text_mode != "none" else []
        media_policy["functional_text_source_locked"] = image_text_mode != "none"
        media_policy["information_allocation"] = content_allocation
        media_policy["image_generation_mode"] = effective_image_mode
        media_policy["image_text_layout"] = image_text_layout
        if image_source == "ai_generated":
            media_policy["generation_model"] = runtime_model
            media_policy["generation_model_label"] = runtime_model_label
    hero = spec.get("hero")
    if isinstance(hero, dict):
        hero["image_generation_mode"] = effective_image_mode
        if image_text_mode != "none":
            hero["text_in_image"] = image_text_mode
            hero["functional_text"] = image_text_checklist
            hero["functional_text_source_locked"] = True
            hero["information_allocation"] = content_allocation
            hero["image_text_layout"] = image_text_layout
    close_design_decisions(spec, design, decision_log)
    return spec
