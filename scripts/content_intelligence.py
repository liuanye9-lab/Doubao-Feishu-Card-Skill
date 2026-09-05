#!/usr/bin/env python3
"""Small, deterministic content-intelligence helpers for the card skill.

This module is intentionally not a copywriter.  It labels source spans so the
layout engine can give attention to the right information without changing the
facts.  Every display-only change remains explainable to a human in the
generated spec.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from visual_spec import extract_metrics, extract_relationship_nodes


# These are explicit user-facing placeholders, not guessed prose.  They are
# safe to turn into a real Emoji because the bracketed token already declares
# that intent.
EMOJI_ALIASES: Dict[str, str] = {
    "[喇叭]": "📣",
    "【喇叭】": "📣",
    "[公告]": "📣",
    "【公告】": "📣",
    "[通知]": "📣",
    "【通知】": "📣",
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
    "[模版]": "🧩",
    "【模版】": "🧩",
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
    "[警告]": "⚠️",
    "【警告】": "⚠️",
    "[完成]": "✅",
    "【完成】": "✅",
}

SEMANTIC_EMOJI: Sequence[Tuple[Tuple[str, ...], str]] = (
    (("截止", "最后", "逾期", "务必", "必须", "风险", "警告"), "⏳"),
    (("背景", "痛点", "挑战", "阻塞"), "⚠️"),
    (("做法", "方法", "机制", "行动"), "🛠️"),
    (("报名", "招募", "宣发", "公告", "通知"), "📣"),
    (("培训", "课程", "学习", "教程", "讲师"), "📚"),
    (("时间线", "日程", "节点", "日期", "流程", "阶段"), "🗓️"),
    (("地点", "地址", "线下", "现场"), "📍"),
    (("模板", "模版", "搭建", "步骤", "材料"), "🧩"),
    (("答疑", "分享", "问题", "交流", "讨论"), "💬"),
    (("提交", "完成", "初赛", "交付"), "🏁"),
    (("作品", "案例", "展示", "成果", "画廊"), "🖼️"),
    (("决赛", "路演", "发布", "发射"), "🚀"),
    (("结果", "颁奖", "获奖", "排名"), "🏆"),
    (("提醒", "重要", "注意"), "🔔"),
    (("公司", "企业", "门店"), "🏢"),
    (("部门", "团队", "员工", "选手", "成员"), "👥"),
    (("方向", "方案", "能力"), "🧭"),
    (("当前状态", "状态", "进度"), "✅"),
    (("数据", "指标", "完成率", "留存率", "耗时", "效果"), "📊"),
    (("查看", "打开", "详情", "链接"), "🔗"),
)

URL_RE = re.compile(r"(?P<url>(?:https?://|lark://|feishu://)[^\s<>\"'“”‘’]+)", re.I)
IMAGE_MARKER_RE = re.compile(r"!\[(?P<alt>[^]]*)\]\((?P<source>[^)]+)\)")

# The order is significant: a full year/date is consumed before a compact
# four-digit date.  0809 and 8.9 are accepted as dates per the skill contract;
# 0800 and 14:00 remain time-like values and are not converted.
DATE_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?P<year>20\d{2}[年./-]\d{1,2}(?:月|[./-])\d{1,2}(?:日|号)?)"
    r"|(?P<chinese>\d{1,2}月\d{1,2}(?:日|号)?)"
    r"|(?P<numeric>\d{1,2}[./-]\d{1,2})"
    r"|(?P<compact>(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01]))"
    r"(?![A-Za-z0-9])"
)

DATE_WORDS = ("日期", "时间", "截止", "开始", "结束", "报名", "提交", "活动", "培训", "日程", "节点", "今天", "明天")
WARNING_WORDS = ("截止", "最后", "务必", "必须", "紧急", "重要", "风险", "警告", "逾期", "deadline", "urgent", "warning", "must")
ACTION_WORDS = ("报名", "注册", "参加", "提交", "查看", "打开", "下载", "领取", "申请", "预约", "确认", "参与", "加入", "了解", "进入", "填写", "回放", "订阅", "开始", "register", "submit", "view", "download", "apply", "join")
STRONG_ACTION_WORDS = ("报名", "注册", "参加", "提交", "申请", "预约", "确认", "加入", "领取", "填写", "订阅", "submit", "register", "apply", "join")
PASSIVE_LINK_WORDS = ("来源", "参考", "引用", "原文", "资料来源", "详情见", "网址如下", "链接如下", "时间", "日期", "截止", "报名时间", "提交时间", "活动时间")
VISUAL_WORDS = ("案例", "作品", "展示", "画廊", "海报", "品牌", "视觉", "产品", "设计", "摄影", "氛围", "配图", "图文", "动图", "gif", "showcase", "portfolio", "gallery", "brand", "visual", "product")
# “作品” frequently appears in plain instructions such as “提交作品模板”.
# It is a visual signal only when the copy also asks readers to see, compare,
# or understand a concrete object.
STRONG_VISUAL_WORDS = ("案例", "展示", "画廊", "海报", "品牌", "视觉", "产品", "设计", "摄影", "氛围", "配图", "图文", "动图", "gif", "showcase", "portfolio", "gallery", "brand", "visual", "product")
TIMELINE_WORDS = ("时间线", "流程", "日程", "节点", "阶段", "timeline", "schedule", "第一步", "第二步", "步骤")
IMAGE_REQUEST_WORDS = ("图片", "配图", "海报", "封面", "首图", "信息图", "图示", "看板", "banner", "hero image", "infographic")
NO_IMAGE_RE = re.compile(r"(?:不要|不需要|无需|不用|去掉|取消)\s*(?:生成)?\s*(?:图片|配图|海报|封面|首图|信息图|动图|GIF)|\bno[- ]?image\b", re.I)


def clean_url(url: str) -> str:
    return url.rstrip("。，、；;：:）)】]}>\"'．")


def normalize_emoji_aliases(value: Any) -> Any:
    """Replace explicit aliases recursively, leaving all other text intact."""
    if isinstance(value, str):
        for alias, emoji in EMOJI_ALIASES.items():
            value = value.replace(alias, emoji)
        return value
    if isinstance(value, list):
        return [normalize_emoji_aliases(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_emoji_aliases(item) for key, item in value.items()}
    return value


def emoji_alias_changes(text: str) -> List[Dict[str, str]]:
    changes: List[Dict[str, str]] = []
    for alias, emoji in EMOJI_ALIASES.items():
        if alias in text:
            changes.append({"source": alias, "output": emoji, "reason": "explicit_icon_alias"})
    return changes


def has_emoji(text: str) -> bool:
    # This covers the pictographs used by the skill without relying on the
    # optional third-party ``regex`` package.
    return bool(re.search(r"[\U0001F1E6-\U0001FAFF\u2300-\u27BF]", text or ""))


def semantic_emoji(text: str, default: str = "💬") -> str:
    value = str(text or "")
    if re.match(r"^(?:一句话(?:介绍|价值)|核心价值|结论|摘要)", value):
        return "💡"
    if re.search(r"功能|模块|机制|方法", value[:16]):
        return "🧩"
    for keywords, emoji in SEMANTIC_EMOJI:
        if any(keyword.lower() in value.lower() for keyword in keywords):
            return emoji
    return default


def ensure_paragraph_emoji(text: str, *, enabled: bool = True) -> Tuple[str, Optional[str]]:
    """Give a rendered paragraph one semantic marker, never two or more."""
    value = str(text or "").strip()
    if not enabled or not value or has_emoji(value):
        return value, None
    emoji = semantic_emoji(value)
    return f"{emoji} {value}", emoji


def split_for_layout(text: str, max_chars: int = 120) -> List[str]:
    """Split long display paragraphs without summarizing or dropping text."""
    value = str(text or "").strip()
    if len(value) <= max_chars:
        return [value] if value else []
    sentence_parts = [part for part in re.split(r"(?<=[。！？；])", value) if part]
    chunks: List[str] = []
    current = ""
    for part in sentence_parts:
        if current and len(current) + len(part) > max_chars:
            chunks.append(current)
            current = ""
        while len(part) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(part[:max_chars])
            part = part[max_chars:]
        current += part
    if current:
        chunks.append(current)
    return chunks or [value]


def _date_display(match: re.Match[str]) -> Optional[str]:
    raw = match.group(0)
    if match.group("year"):
        found = re.search(r"20\d{2}[年./-](\d{1,2})(?:月|[./-])(\d{1,2})", raw)
        if not found:
            return None
        month, day = int(found.group(1)), int(found.group(2))
    elif match.group("chinese"):
        found = re.fullmatch(r"(\d{1,2})月(\d{1,2})(?:日|号)?", raw)
        if not found:
            return None
        month, day = int(found.group(1)), int(found.group(2))
    elif match.group("numeric"):
        found = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})", raw)
        if not found:
            return None
        month, day = int(found.group(1)), int(found.group(2))
    else:
        month, day = int(raw[:2]), int(raw[2:])
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return f"{month}月{day}日"


def normalize_dates(text: str) -> Tuple[str, List[Dict[str, str]]]:
    """Canonicalize dates to ``几月几日`` and return a transformation ledger."""
    transformations: List[Dict[str, str]] = []
    value = str(text or "")

    def replace(match: re.Match[str]) -> str:
        display = _date_display(match)
        if not display or display == match.group(0):
            return match.group(0)
        transformations.append({
            "kind": "date_normalize",
            "source": match.group(0),
            "output": display,
            "reason": "canonical_date_display",
        })
        return display

    return DATE_TOKEN_RE.sub(replace, value), transformations


def extract_date_candidates(text: str) -> List[Dict[str, str]]:
    candidates: List[Dict[str, str]] = []
    for match in DATE_TOKEN_RE.finditer(str(text or "")):
        display = _date_display(match)
        if display:
            candidates.append({"source": match.group(0), "display": display, "start": str(match.start()), "end": str(match.end())})
    return candidates


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9]+", value.lower()))


def text_similarity(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    return len(a & b) / max(1, len(a | b)) if a and b else 0.0


def high_confidence_duplicate(left: str, right: str) -> bool:
    """Return true only for a display-safe duplicate, not a paraphrase."""
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return False
    normalized_left = re.sub(r"[\s，。；：、,.!?！？]+", "", left.lower())
    normalized_right = re.sub(r"[\s，。；：、,.!?！？]+", "", right.lower())
    return (
        normalized_left == normalized_right
        or (text_similarity(left, right) >= 0.94 and abs(len(left) - len(right)) <= 8 and (a <= b or b <= a))
    )


def infer_action_label(context: str) -> str:
    value = context.lower()
    if any(word in value for word in ("报名", "注册", "参加", "join", "register")):
        return "立即报名"
    if any(phrase in value for phrase in ("查看作品", "打开作品", "作品详情")):
        return "查看作品"
    if any(word in value for word in ("提交", "交付", "作品", "submit")):
        return "提交作品"
    if any(word in value for word in ("培训", "课程", "教程", "training", "course")):
        return "查看培训"
    if any(word in value for word in ("模板", "模版", "下载", "download")):
        return "下载模板"
    if any(word in value for word in ("预约", "直播", "calendar")):
        return "立即预约"
    if any(word in value for word in ("查看", "详情", "了解", "view")):
        return "查看详情"
    return "打开链接"


def _button_priority(context: str) -> Tuple[int, List[str]]:
    """Score whether a URL represents a useful next action.

    A URL is not automatically a button.  The surrounding copy must tell the
    reader what to do; otherwise the URL stays visible as an inline reference.
    """
    value = str(context or "").lower()
    strong = [word for word in STRONG_ACTION_WORDS if word.lower() in value]
    ordinary = [word for word in ACTION_WORDS if word.lower() in value]
    passive = [word for word in PASSIVE_LINK_WORDS if word.lower() in value]
    explicit_cue = bool(re.search(r"(?:请|立即|点击|前往|进入|填写|领取|报名入口|提交入口|下载|预约|join|register|submit|apply)", value, re.I))
    if passive and not explicit_cue:
        return 0, passive
    if strong:
        return 3, strong
    if ordinary and not (passive and not re.search(r"(?:点击|立即|前往|进入|请|可)", value)):
        return 2, ordinary
    return 0, passive


def _has_explicit_action_cue(line: str) -> bool:
    """Recognize an actual CTA request, not a noun such as “报名时间”."""
    value = str(line or "").lower()
    return bool(re.search(r"(?:请|立即|点击|前往|进入|填写|领取|报名入口|提交入口|下载|预约|join|register|submit|apply)", value, re.I))


def suggest_buttons(lines: Sequence[str], *, scene: Optional[str] = None) -> List[Dict[str, Any]]:
    suggestions: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for index, line in enumerate(lines):
        for match in URL_RE.finditer(line):
            url = clean_url(match.group("url"))
            if not url or url in seen:
                continue
            seen.add(url)
            context = line.replace(match.group(0), " ")
            priority, action_words = _button_priority(context)
            suggestions.append({
                "label": infer_action_label(context),
                "url": url,
                "source_text": line,
                "source_line": index + 1,
                "surface": "open_url" if priority else "inline_url",
                "button_eligible": bool(priority),
                "priority": priority,
                "action_words": action_words,
                "selected": False,
                "reason": (
                    "真实 URL 伴随明确行动语义，按钮能缩短下一步路径"
                    if priority
                    else "URL 只是来源/参考或缺少明确动作，保留为行内链接，不强行做按钮"
                ),
            })

    # In a case-showcase card the source field “初赛作品链接” is the review
    # destination the reader needs next.  This is a narrow presentation rule,
    # not a general “every URL becomes a button” shortcut; other scenes keep
    # the passive-link behavior above.
    if scene == "case-showcase":
        for item in suggestions:
            source_text = str(item.get("source_text") or "")
            if item.get("url") and re.search(r"作品\s*链接", source_text):
                item.update({
                    "label": "查看作品",
                    "surface": "open_url",
                    "button_eligible": True,
                    "priority": 3,
                    "action_words": ["查看"],
                    "reason": "case-showcase 中真实作品链接作为评审/查看动作，按用户请求转为原生按钮",
                })

    eligible = [item for item in suggestions if item.get("button_eligible")]
    eligible_order = sorted(
        range(len(eligible)),
        key=lambda position: (-int(eligible[position].get("priority", 0)), int(eligible[position].get("source_line", 0))),
    )
    selected_positions = set(eligible_order[:2])
    for position, item in enumerate(eligible):
        item["selected"] = position in selected_positions
        if item["selected"]:
            item["button_kind"] = "primary" if position == eligible_order[0] else "secondary"
            item["reason"] = "真实 URL + 明确动作；按一个主动作、最多一个次动作控制移动端密度" if position == eligible_order[0] else "真实 URL + 明确动作；作为次要动作保留"
        else:
            item["reason"] = "动作候选超过移动端预算；不生成按钮，保留 URL 的原文语境"
    # A missing target is worth surfacing only when the source line is an
    # imperative CTA. Words such as “报名” in “感谢大家报名” or “提交作品”
    # as a timeline milestone are facts, not button requests.
    if not any(item.get("button_eligible") for item in suggestions):
        for index, line in enumerate(lines):
            if _has_explicit_action_cue(line) and any(word.lower() in line.lower() for word in ACTION_WORDS):
                suggestions.append({
                    "label": infer_action_label(line),
                    "url": None,
                    "source_text": line,
                    "source_line": index + 1,
                    "surface": "needs_url_or_callback",
                    "button_eligible": False,
                    "priority": 0,
                    "action_words": [word for word in ACTION_WORDS if word.lower() in line.lower()],
                    "selected": False,
                    "reason": "检测到明确行动语句，但没有真实 URL；不虚构跳转目标",
                })
                break
    return suggestions


def _visual_label(value: Any, *, strip_marker: bool = True) -> str:
    text = str(value or "").strip()
    if strip_marker:
        text = re.sub(r"^\s*(?:[-*•]|\d+[.)、])\s*", "", text)
        text = re.sub(r"^[📣🫶📅🗓️⏰📍🔗🧩💬🏁🖼️🔔📚📝⏳🚀🏆⚠️✅💡✨🎓📄]\s*", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _walk_blocks(blocks: Any) -> Iterable[Dict[str, Any]]:
    if not isinstance(blocks, list):
        return
    for block in blocks:
        if not isinstance(block, dict):
            continue
        yield block
        children = block.get("blocks", block.get("elements", []))
        yield from _walk_blocks(children)


def _block_source_lines(block: Mapping[str, Any]) -> List[str]:
    source_lines = block.get("source_lines")
    if isinstance(source_lines, list):
        return [str(line) for line in source_lines if str(line).strip()]
    source_text = str(block.get("source_text") or "").strip()
    return [source_text] if source_text else []


def _inferred_title(lines: Sequence[str], explicit_title: Optional[str] = None) -> str:
    """Prefer a topic title over a social greeting when one is available."""
    if explicit_title and str(explicit_title).strip():
        return _visual_label(explicit_title)
    if not lines:
        return ""
    first = _visual_label(lines[0])
    if not re.match(r"^(?:hello|hi|hey|嗨|你好|大家好|各位|朋友们)", first, re.I):
        return first
    for line in lines[1:8]:
        candidate = _visual_label(line)
        for anchor in ("AI先锋大赛", "先锋大赛"):
            anchor_position = candidate.find(anchor)
            if anchor_position >= 0:
                focused = re.split(r"[，。！？!?；;]", candidate[anchor_position:])[0].strip()
                if focused:
                    return focused[:48]
        if any(word in candidate for word in ("开营", "培训", "课程", "活动", "项目", "案例", "产品", "发布")):
            candidate = re.sub(r"^(?:感谢大家[^！!。]*[！!。]|我们)", "", candidate).strip()
            candidate = re.split(r"[，。！？!?；;]", candidate)[0].strip()
            if candidate:
                return candidate[:48]
    return first


def build_image_text_items(blocks: Sequence[Dict[str, Any]], title: str) -> List[Dict[str, Any]]:
    """Choose concise, source-backed labels for an information-bearing image.

    This is intentionally narrower than the native Card content.  The image
    gets the relationship a reader scans fastest; paragraphs and exact detail
    remain in the editable Card layer.
    """
    items: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def add(role: str, text: Any, source_lines: Sequence[str], why: str) -> None:
        label = _visual_label(text, strip_marker=role not in {"quote", "cta"})
        if not label or label in seen:
            return
        seen.add(label)
        items.append({
            "role": role,
            "text": label,
            "source_text": "\n".join(str(line) for line in source_lines if str(line).strip()) or str(text),
            "source_lines": [str(line) for line in source_lines if str(line).strip()],
            "why": why,
        })

    clean_title = _visual_label(title)
    if clean_title and len(clean_title) <= 48:
        add("title", clean_title, [title], "图片需要一个短主题锚点，帮助读者先判断卡片在讲什么")

    flat = list(_walk_blocks(blocks))

    def add_case_relationship(raw_text: Any, source_lines: Sequence[str]) -> None:
        """Promote compact source-backed case nodes into the image whitelist.

        Case cards frequently arrive as plain text rather than structured
        ``section`` blocks.  The native Card still keeps the full sentence;
        Seedream 5.0 Pro receives only the first source-backed clause so the bitmap can
        summarize the background -> method -> result relationship without
        inventing copy or turning into a dense paragraph.
        """
        for raw_line in str(raw_text or "").splitlines():
            line = raw_line.strip()
            match = re.match(r"^(背景(?:/[^：:]+)?|做法|结果(?:/价值)?)[：:]\s*(.+)$", line)
            if not match:
                continue
            label, body = match.groups()
            body = _visual_label(body)
            if not body:
                continue
            compact = re.split(r"[。！？!?；;]", body, maxsplit=1)[0].strip()
            if not compact:
                compact = body
            add(
                "relationship",
                f"{label}：{compact}",
                list(source_lines) or [line],
                "案例的背景—做法—结果关系比完整说明段更适合先用图建立认知",
            )

    def compact_case_body(value: Any) -> str:
        """Keep the first source-backed clause readable in a mobile bitmap."""
        body = _visual_label(value)
        if not body:
            return ""
        return re.split(r"[。！？!?；;]", body, maxsplit=1)[0].strip() or body

    # A number of registrations are flattened to text blocks. Recover their
    # explicit case labels before the generic fact/timeline pass.
    for block in flat:
        if block.get("type") == "text":
            content = block.get("content") or block.get("text") or ""
            add_case_relationship(content, _block_source_lines(block) or [str(content)])
        elif block.get("type") == "section":
            section_title = _visual_label(block.get("title"))
            body = str(block.get("body") or block.get("content") or "")
            source_lines = _block_source_lines(block) or body.splitlines()
            case_title = re.match(r"^(背景(?:/[^：:]+)?|做法|结果(?:/价值)?)$", section_title)
            if case_title:
                # Keep the three case nodes in source order. For a numbered
                # method section, use its first source-backed action; the
                # native Card retains every numbered method and its full copy.
                candidate = body
                if section_title == "做法":
                    action_lines = [
                        re.sub(r"^\s*\d+[.)、]\s*", "", line.strip())
                        for line in body.splitlines()
                        if line.strip() and not re.match(r"^\s*结果(?:/价值)?[：:]", line.strip())
                    ]
                    candidate = action_lines[0] if action_lines else body
                compact = compact_case_body(candidate)
                add(
                    "relationship",
                    f"{section_title}：{compact}" if compact else section_title,
                    source_lines,
                    "案例的背景—做法—结果关系比完整说明段更适合先用图建立认知",
                )
            else:
                add_case_relationship(body, source_lines)

    timelines = [block for block in flat if block.get("type") == "timeline"]
    if timelines:
        for timeline in timelines:
            for item in timeline.get("items", []):
                if not isinstance(item, dict):
                    continue
                parts: List[str] = []
                date = _visual_label(item.get("date"))
                if date:
                    parts.append(date)
                item_title = _visual_label(item.get("title"))
                if item_title and item_title not in parts:
                    parts.append(item_title)
                body = str(item.get("body") or item.get("content") or "")
                for line in body.splitlines()[:2]:
                    label = _visual_label(line)
                    if label and label not in parts:
                        parts.append(label)
                add("stage", "\n".join(parts[:3]), _block_source_lines(item), "日期、阶段和动作之间的顺序最适合用节点关系快速传达")
                if len([entry for entry in items if entry.get("role") == "stage"]) >= 4:
                    break
            if len([entry for entry in items if entry.get("role") == "stage"]) >= 4:
                break

    metrics = [block for block in flat if block.get("type") == "metrics"]
    for metric_block in metrics:
        for item in metric_block.get("items", [])[:4]:
            if not isinstance(item, dict):
                continue
            label = _visual_label(item.get("label", item.get("metric")))
            value = _visual_label(item.get("value"))
            add("metric", "：".join(part for part in (label, value) if part), _block_source_lines(item), "短标签和数值的比较关系适合做成信息指标，而不是长段落")

    if not timelines and not metrics:
        facts = [block for block in flat if block.get("type") == "facts"]
        for fact_block in facts:
            for item in fact_block.get("items", [])[:4]:
                if not isinstance(item, dict):
                    continue
                label = _visual_label(item.get("label"))
                value = _visual_label(item.get("value"))
                if len("：".join(part for part in (label, value) if part)) <= 64:
                    add("fact", "：".join(part for part in (label, value) if part), _block_source_lines(item), "短事实可以帮助读者快速定位状态或关键属性")

    case_words = ("背景", "问题", "做法", "结果", "成果", "方法", "前", "后")
    for block in flat:
        if block.get("type") != "section":
            continue
        section_title = _visual_label(block.get("title"))
        has_full_case_node = any(
            entry.get("role") == "relationship"
            and str(entry.get("text") or "").startswith(f"{section_title}：")
            for entry in items
        )
        if section_title and any(word in section_title for word in case_words) and not has_full_case_node:
            add("relationship", section_title, _block_source_lines(block), "案例的背景—做法—结果关系比完整说明段更适合先用图建立认知")
        if len([entry for entry in items if entry.get("role") == "relationship"]) >= 3:
            break

    for block in flat:
        if block.get("type") != "quote":
            continue
        quote = _visual_label(block.get("text"), strip_marker=False)
        if quote and len(quote) <= 96:
            add("quote", quote, _block_source_lines(block), "短而明确的理念寄语可以作为视觉收束；过长寄语留在原生 Card")
        break
    return items


def _source_image_candidates(lines: Sequence[str], title: str) -> List[Dict[str, Any]]:
    """Build a preliminary allocation before the Card blocks are materialized."""
    items: List[Dict[str, Any]] = []
    if _visual_label(title) and len(_visual_label(title)) <= 48:
        items.append({"role": "title", "text": _visual_label(title), "source_text": title, "source_lines": [title], "why": "短主题锚点"})
    for line in lines:
        if extract_date_candidates(line) or re.match(r"^\s*(?:第\s*[一二三四五六七八九十]+\s*步|步骤\s*\d+|step\s*\d+)\b", line, re.I):
            items.append({"role": "stage", "text": _visual_label(line), "source_text": line, "source_lines": [line], "why": "日期/步骤关系"})
        elif re.match(r"^\s*[^：:|｜\t]{1,14}\s*[：:]\s*[+-]?\d", line):
            items.append({"role": "metric", "text": _visual_label(line), "source_text": line, "source_lines": [line], "why": "短标签数值关系"})
        if len(items) >= 6:
            break
    return items


def build_information_allocation(
    source: str,
    *,
    scene: Optional[str] = None,
    title: Optional[str] = None,
    blocks: Optional[Sequence[Dict[str, Any]]] = None,
    button_suggestions: Optional[Sequence[Dict[str, Any]]] = None,
    explicit_media: bool = False,
    supplied_media: bool = False,
    force_no_image: bool = False,
) -> Dict[str, Any]:
    """Decide which source spans belong in Seedream 5.0 Pro, native Card, or buttons."""
    value = str(source or "")
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    resolved_title = _inferred_title(lines, title)
    dates = extract_date_candidates(value)
    date_lines = [line for line in lines if extract_date_candidates(line)]
    step_lines = [line for line in lines if re.match(r"^\s*(?:[-*•]|\d+[.)、]|第\s*[一二三四五六七八九十]+\s*步|步骤\s*\d+|step\s*\d+)", line, re.I)]
    explicit_step_lines = [line for line in lines if re.match(r"^\s*(?:第\s*[一二三四五六七八九十]+\s*步|步骤\s*\d+|step\s*\d+)\b", line, re.I)]
    metric_records = extract_metrics(value)
    metric_lines = [item["source_text"] for item in metric_records]
    relationship_words = ("背景", "问题", "做法", "结果", "成果", "前后", "对比", "路径", "关系", "看板", "指标")
    relationship_hits = [word for word in relationship_words if word.lower() in value.lower()]
    visual_hits = [word for word in VISUAL_WORDS if word.lower() in value.lower()]
    strong_visual_hits = [word for word in STRONG_VISUAL_WORDS if word.lower() in value.lower()]
    if "作品" in value and re.search(r"作品\s*(?:展示|集)|展示\s*作品|作品\s*(?:对比|案例)", value, re.I):
        strong_visual_hits.append("作品展示")
    no_image = bool(NO_IMAGE_RE.search(value))
    timeline_signal = len(dates) >= 2 or (bool(date_lines) and bool(re.search("|".join(map(re.escape, TIMELINE_WORDS)), value, re.I))) or len(explicit_step_lines) >= 2 or (len(step_lines) >= 2 and bool(re.search("|".join(map(re.escape, TIMELINE_WORDS)), value, re.I)))
    metric_signal = len(metric_lines) >= 2
    case_signal = len(set(relationship_hits)) >= 2
    explicit_visual_request = explicit_media or bool(re.search("|".join(map(re.escape, IMAGE_REQUEST_WORDS)), value, re.I))
    # A visual is the stable default.  If the source has no data/process/
    # comparison signal, Seedream 5.0 Pro still creates one thematic information visual;
    # only an explicit no-image request disables it.
    image_use = True
    if no_image or force_no_image:
        image_use = False

    reasons: List[str] = []
    if timeline_signal:
        reasons.append("日期/阶段/步骤之间存在顺序关系，时间轴比连续文字更快建立全局认识")
    if metric_signal:
        reasons.append("存在至少两组短标签与数值，指标卡比段落更利于比较")
    if case_signal:
        reasons.append("存在背景/问题/做法/结果等关系词，关系图比平铺叙述更高效")
    if explicit_visual_request or supplied_media:
        reasons.append("用户或原文明确要求视觉媒介，图片承担主题或证据任务")
    if strong_visual_hits and not reasons:
        reasons.append("原文包含案例/产品/作品等视觉对象，图片可先建立主题锚点")
    if no_image or force_no_image:
        reasons = ["用户或设计计划明确要求不使用图片；原生 Card 保留精简摘要和真实行动，完整事实仍在 source.txt"]
    if not reasons:
        reasons = ["默认生成一张主题信息视觉，建立首屏认知；不编造数据或额外事实"]

    if no_image or force_no_image:
        image_job = "不设置图片任务"
    elif timeline_signal:
        image_job = "让读者先看懂日期、阶段、动作和下一节点的顺序"
    elif metric_signal:
        image_job = "让读者先比较关键指标及其变化关系"
    elif case_signal:
        image_job = "让读者先看懂背景/问题到做法/结果的关系"
    elif supplied_media or explicit_visual_request or strong_visual_hits:
        image_job = "用一个主题或证据视觉建立快速认知，不替代完整事实"
    else:
        image_job = "用一张主题信息视觉建立快速认知，不伪造数据或按钮"

    suggestions = list(button_suggestions or suggest_buttons(lines, scene=scene))
    eligible_buttons = [item for item in suggestions if item.get("button_eligible") and item.get("selected")]
    pending_buttons = [item for item in suggestions if item.get("surface") == "needs_url_or_callback"]
    not_buttons = [item for item in suggestions if not item.get("selected")]
    image_items = build_image_text_items(blocks or [], resolved_title) if blocks is not None else _source_image_candidates(lines, resolved_title)
    # Always merge source-backed metrics and steps, even when native blocks
    # were compacted or a scene omitted their component type.
    for metric in metric_records[:4]:
        label = str(metric["source_text"])
        if not any(item.get("text") == label for item in image_items):
            image_items.append({"role": "metric", "text": label, "source_text": label,
                                "source_lines": [label], "why": "来源指标保留原始口径"})
    for node in extract_relationship_nodes(value):
        label = str(node["label"]) + "：" + str(node["text"])
        if not any(item.get("text") == label for item in image_items):
            image_items.append({"role": "relationship", "text": label, "source_text": node["source_text"],
                                "source_lines": [node["source_text"]], "why": "来源步骤或关系"})
    if not image_use:
        excluded_image = image_items
        image_items = []
    else:
        excluded_image = []
        # Keep one title plus a small set of source-backed relationship labels.
        # A case card should show the case skeleton (背景—做法—结果) before
        # spending the image budget on secondary facts; otherwise five facts
        # can crowd all of the story structure out of the bitmap.
        eligible = []
        for item in image_items:
            if len(str(item.get("text") or "")) > 96:
                excluded_image.append({**item, "excluded_reason": "文字过长，原生 Card 更适合完整阅读"})
                continue
            eligible.append(item)
        if scene == "case-showcase":
            title_items = [item for item in eligible if item.get("role") == "title"]
            relationship_items = [item for item in eligible if item.get("role") == "relationship"]
            fact_items = [item for item in eligible if item.get("role") == "fact"]
            preferred_fact_labels = ("主题", "状态", "形式", "对象", "地点")
            fact_items.sort(
                key=lambda item: next(
                    (index for index, label in enumerate(preferred_fact_labels) if str(item.get("text") or "").startswith(f"{label}：")),
                    len(preferred_fact_labels),
                )
            )
            quote_items = [item for item in eligible if item.get("role") == "quote"]
            metric_items = [item for item in eligible if item.get("role") == "metric"]
            image_items = (title_items[:1] + relationship_items[:3] + quote_items[:1] + metric_items[:4] + fact_items[:2])[:7]
            selected_ids = {id(item) for item in image_items}
            excluded_image.extend(
                {**item, "excluded_reason": "case-showcase 优先保留背景—做法—结果关系"}
                for item in eligible
                if id(item) not in selected_ids
            )
        else:
            image_items = eligible[:7]

    image_lines = sorted({line for item in image_items for line in item.get("source_lines", []) if str(line).strip()})
    native_roles = ["一句核心摘要和 3–5 个关键点", "来源锁定的指标/图表结论", "可编辑/可访问的精确日期、数字、姓名和引用"]
    if image_use:
        native_roles.append("图片未承载的必要关键事实；长文全文保留在 source.txt，有真实来源链接时由原生按钮打开")
    if eligible_buttons:
        native_roles.append("真实 URL 与点击行为由原生 Card 按钮承载")
    if pending_buttons:
        native_roles.append("无目标的行动语句先保留为文字，等待真实 URL 或 application Bot 回调")

    return {
        "version": "1",
        "strategy": "image_native_button_allocation",
        "decision": "image_plus_native" if image_use else "native_only",
        "scene": scene,
        "title": resolved_title,
        "image": {
            "use": image_use,
            "job": image_job,
            "reason": "；".join(reasons),
            "include": image_items,
            "exclude": excluded_image,
            "text_budget": "短标题 + 最多 4 个关系节点/指标 + 最多 1 个短 quote；不包含按钮、CTA 标签或伪交互",
            "text_policy": "seedream_5_pro_direct_selected_text_and_layout" if image_use and image_items else "none",
            "not_for": ["问候语", "长段落", "规则细节", "完整说明", "仅供参考的 URL", "没有关系任务的普通文字", "按钮/CTA 标签", "按钮形控件或伪交互"],
        },
        "native_card": {
            "use": True,
            "reason": "原生 Card 可编辑、可访问、可复制，默认只承载摘要、关键点、来源数据和真实行动",
            "preserve": native_roles,
            "source_line_count": len(lines),
            "source_lines": list(range(1, len(lines) + 1)),
            "image_excluded_source_lines": [index + 1 for index, line in enumerate(lines) if line not in image_lines],
        },
        "buttons": {
            "use": bool(eligible_buttons),
            "reason": "有真实 URL 且上下文明确要求下一步时使用按钮；否则不制造按钮",
            "primary": next((item for item in eligible_buttons if item.get("button_kind") == "primary"), None),
            "secondary": [item for item in eligible_buttons if item.get("button_kind") == "secondary"],
            "pending": pending_buttons,
            "not_used": not_buttons,
            "budget": "最多 1 个 primary + 1 个 secondary",
            "native_behavior": "open_url 或 application Bot callback；所有真实交互只在原生 Card，图片不绘制 CTA 或按钮",
        },
        "signals": {
            "date_count": len(dates),
            "date_line_count": len(date_lines),
            "step_line_count": len(step_lines),
            "metric_line_count": len(metric_lines),
            "timeline_signal": timeline_signal,
            "metric_signal": metric_signal,
            "case_signal": case_signal,
            "explicit_visual_request": explicit_visual_request,
            "image_use": image_use,
            "relationship_hits": relationship_hits,
            "visual_hits": visual_hits,
            "strong_visual_hits": strong_visual_hits,
            "explicit_step_count": len(explicit_step_lines),
            "no_image_request": no_image or force_no_image,
        },
    }


def _line_role(line: str, index: int, *, date_count: int, url_count: int, scene: Optional[str]) -> Tuple[str, str, List[str]]:
    lowered = line.lower()
    if index == 0:
        return "title", "P0", ["heading", "single_focus"]
    if any(word.lower() in lowered for word in WARNING_WORDS) and extract_date_candidates(line):
        return "deadline", "P0", ["date_size", "bold", "semantic_color", "alert_marker"]
    if extract_date_candidates(line) and (date_count >= 2 or scene == "activity-timeline"):
        return "timeline_date", "P0", ["date_size", "bold", "underline_in_preview"]
    if any(word.lower() in lowered for word in ACTION_WORDS):
        return "action", "P1", ["bold_action", "primary_cta_if_url"]
    if url_count and URL_RE.search(line):
        return "link", "P1", ["button_route"]
    if any(word.lower() in lowered for word in VISUAL_WORDS):
        return "visual_context", "P2", ["image_or_infographic_candidate"]
    return "supporting", "P2", ["normal_text", "progressive_disclosure_candidate"]


def build_attention_map(lines: Sequence[str], *, scene: Optional[str] = None) -> Dict[str, Any]:
    date_count = len(extract_date_candidates("\n".join(lines)))
    url_count = len({clean_url(m.group("url")) for line in lines for m in URL_RE.finditer(line)})
    units: List[Dict[str, Any]] = []
    for index, line in enumerate(lines):
        role, priority, treatment = _line_role(line, index, date_count=date_count, url_count=url_count, scene=scene)
        units.append({
            "line": index + 1,
            "source_text": line,
            "role": role,
            "priority": priority,
            "treatment": treatment,
        })
    primary = [unit for unit in units if unit["priority"] == "P0"]
    if date_count >= 2 or scene == "activity-timeline":
        focus = "时间与动作"
        attention_order = ["时间/截止", "阶段/事项", "完成动作", "补充说明"]
    elif any(unit["role"] == "deadline" for unit in units):
        focus = "截止与行动"
        attention_order = ["截止时间", "必须完成的动作", "完成方式", "补充说明"]
    elif url_count:
        focus = "主题与行动入口"
        attention_order = ["主题", "要做什么", "行动入口", "补充说明"]
    else:
        focus = "主题与下一步"
        attention_order = ["主题", "当前状态", "下一步", "补充说明"]
    return {
        "focus": focus,
        "attention_order": attention_order,
        "single_focus_rule": "一张卡只保留一个最大焦点；日期/截止与动作优先于装饰",
        "units": units,
        "primary_units": [unit["line"] for unit in primary],
        "card_emphasis": {
            "strong": ["title", "deadline", "timeline_date", "primary_action"],
            "medium": ["action", "link", "status"],
            "quiet": ["supporting", "source", "footer"],
            "underline": "仅在本地编辑预览中使用；Card 2.0 默认用加粗+语义色+结构块安全降级",
        },
    }


def _promotion_variables(source: str) -> List[str]:
    variables: List[str] = []
    if "场景" in source:
        variables.append("场景")
    if "作品" in source or "案例" in source:
        variables.append("作品名称")
    variables.append("提交人")
    return variables


def build_promotion_copy(source: str, title: str, attention: Dict[str, Any]) -> List[Dict[str, Any]]:
    variables = _promotion_variables(source)
    return [
        {
            "kind": "pre_card_group_hook",
            "text": "📣 朋友们快来看看：{提交人}提交的【{场景/作品名称}】千万别错过！",
            "variables": variables,
            "source_basis": [title] if title else [],
            "requires_human_review": True,
            "delivery": "群消息前置话术，不自动写入卡片正文",
        },
        {
            "kind": "one_line_summary",
            "text": f"👀 先看{attention.get('focus', '主题与下一步')}，再点卡片入口。",
            "variables": [],
            "source_basis": [title] if title else [],
            "requires_human_review": True,
            "delivery": "可选群内引导，不自动发送",
        },
    ]


def _visual_source_spans(lines: Sequence[str]) -> List[str]:
    """Return source lines that can guide an information-bearing visual.

    These spans guide the selected Seedream 5.0 Pro visual. The main pipeline also keeps
    the full source copy for provenance and native Card preservation, but only
    the allocated image text is allowed into the bitmap.
    """
    spans: List[str] = []
    for line in lines:
        if (
            extract_date_candidates(line)
            or any(word.lower() in line.lower() for word in TIMELINE_WORDS)
            or any(word.lower() in line.lower() for word in VISUAL_WORDS)
            or re.match(r"^\s*(?:[-*•]|\d+[.)、])\s+", line)
        ):
            spans.append(line)
    return spans[:8]


def _visual_job(lines: Sequence[str], *, timeline: bool, metric_signal: bool, visual_signal: bool, explicit_media: bool) -> Dict[str, Any]:
    if timeline:
        return {
            "job": "show sequence, grouping, and handoffs between the source's stages",
            "composition": "a clean connected path with distinct visual stations and a clear direction of travel",
            "role": "information_timeline",
        }
    if metric_signal:
        return {
            "job": "show source-backed metrics with their exact units and qualifiers in separate labeled stat tiles; draw comparative charts only from the explicit validated chart plan",
            "composition": "a compact data dashboard paired with the native CardKit chart; never mix incompatible units",
            "role": "information_metrics",
        }
    if visual_signal or explicit_media:
        return {
            "job": "show the source's subject, relationship, or problem-to-action structure",
            "composition": "one concrete subject or relationship map supported by a restrained editorial frame",
            "role": "information_context",
        }
    return {
        "job": "give the topic and next action one visual anchor",
        "composition": "one clear object or spatial relationship, with no decorative icon collage",
        "role": "information_anchor",
    }


def analyze_content(text: str, *, scene: Optional[str] = None) -> Dict[str, Any]:
    """Return source-locked, explainable analysis for a plain-text card."""
    source = str(text or "")
    lines = [line.strip() for line in source.splitlines() if line.strip()]
    title = lines[0].lstrip("# ").strip() if lines else ""
    dates = extract_date_candidates(source)
    urls = [clean_url(match.group("url")) for match in URL_RE.finditer(source)]
    attention = build_attention_map(lines, scene=scene)
    button_suggestions = suggest_buttons(lines, scene=scene)
    visual_signal = bool(any(word.lower() in source.lower() for word in STRONG_VISUAL_WORDS))
    if "作品" in source and re.search(r"作品\s*(?:展示|集)|展示\s*作品|作品\s*(?:对比|案例)", source, re.I):
        visual_signal = True
    explicit_media = bool(IMAGE_MARKER_RE.search(source) or re.search(r"动图|GIF|动画|配图|首图|海报", source, re.I))
    timeline = len(dates) >= 2 or any(word.lower() in source.lower() for word in TIMELINE_WORDS)
    allocation = build_information_allocation(
        source,
        scene=scene,
        button_suggestions=button_suggestions,
        explicit_media=explicit_media,
        supplied_media=bool(IMAGE_MARKER_RE.search(source)),
    )
    allocation_signals = allocation.get("signals", {}) if isinstance(allocation, dict) else {}
    allocated_timeline = bool(allocation_signals.get("timeline_signal"))
    allocated_metrics = bool(allocation_signals.get("metric_signal"))
    if allocation["image"]["use"]:
        media_mode = "infographic" if allocated_timeline else "information_image"
    else:
        media_mode = "none"
    if re.search(r"动图|GIF|动画", source, re.I):
        media_kind = "gif_with_static_first_frame"
    elif media_mode != "none":
        media_kind = "image"
    else:
        media_kind = None
    visual_job = _visual_job(
        lines,
        timeline=allocated_timeline,
        metric_signal=allocated_metrics,
        visual_signal=visual_signal,
        explicit_media=explicit_media,
    )
    return {
        "source_locked": True,
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "rewrite_policy": {
            "factual_text_changed": False,
            "paraphrase": "blocked_without_explicit_user_request",
            "supplement": "blocked_without_explicit_user_request",
            "display_transformations": ["structure", "explicit_emoji_alias", "canonical_date", "safe_high_confidence_dedupe"],
        },
        "title_source": title,
        "date_candidates": dates,
        "button_suggestions": button_suggestions,
        "attention_map": attention,
        "information_allocation": allocation,
        "long_text_policy": {
            "avoid_wall_of_text": True,
            "split": "source-line or sentence boundary when reliable",
            "collapse": "secondary source spans only",
            "never_drop_facts": True,
            "visible_card_budget": "一句摘要 + 3–5 个关键点 + 指标/图表 + CTA",
            "full_source_location": "source.txt; use a real source URL when readers need the full document",
        },
        "media_plan": {
            "mode": media_mode,
            "asset_kind": media_kind,
            "information_carrier": allocation["image"]["use"],
            "not_decorative": allocation["image"]["use"],
            "visual_job": visual_job["job"],
            "composition": visual_job["composition"],
            "role": visual_job["role"],
            "source_spans": [item.get("source_text") for item in allocation["image"]["include"] if item.get("source_text")],
            "native_text_pairing": "place the image beside or immediately before the native fact/timeline block it explains",
            "facts_must_remain_in_text": True,
            "should_use_image": allocation["image"]["use"],
            "text_in_image": allocation["image"]["text_policy"],
            "image_text_layout": "reference_card_banner",
            "functional_text_source": "information_allocation.image.include; complete source copy remains native Card and provenance context",
            "prompt_constraint": "把完整源文案作为事实参考，同时只把 information_allocation.image.include 的选中文字交给 Seedream 5.0 Pro 一次性生成；原生 Card 只保留精简摘要、关键点、图表和真实交互，长文与规则原文保留在 source.txt；禁止无字底图和后处理文字层",
        },
        "promotion_copy": build_promotion_copy(source, title, attention),
    }
