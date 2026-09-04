#!/usr/bin/env python3
"""Conservative content-mode detection and source-preserving grouping.

This is the content-intelligence part absorbed from ``lark-card-studio``.
It is intentionally deterministic: it never invents an owner, deadline,
metric, conclusion, or motivational sentence.  The main layout engine may
use the result to choose sections and fold behavior, while the original text
remains the canonical source.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Optional


MODES = {"notice", "meeting_summary", "work_report", "long_summary"}

_MEETING_TERMS = (
    "会议", "纪要", "讨论", "决议", "会议记录", "行动项", "参会", "发言", "沟通", "同步", "meeting", "minutes",
)
_WORK_TERMS = (
    "工作汇报", "工作总结", "周报", "月报", "本周工作", "本月工作", "进展", "已完成", "进行中", "下一步", "风险", "卡点", "汇报", "交付", "上线", "工作报告",
)
_NOTICE_TERMS = (
    "通知", "公告", "报名", "培训", "课程", "活动", "开营", "时间线", "日程", "安排", "提交", "招募", "发布",
)
_HEADING_MAP = (
    ("topics", ("讨论话题", "会议议题", "议题", "讨论主题")),
    ("confirmed", ("确认事项", "会议决议", "决议", "已确认", "结论")),
    ("todo", ("待办事项", "行动项", "后续工作", "下一步计划", "待跟进")),
    ("overview", ("工作概述", "总结", "概览", "本期概述")),
    ("completed", ("已完成", "完成事项", "已交付", "成果")),
    ("in_progress", ("进行中", "推进中", "当前进展")),
    ("next", ("下一步", "下一步计划", "后续计划", "计划")),
    ("risks", ("风险", "风险/卡点", "卡点", "问题与风险")),
    ("intro", ("说明", "背景", "开场", "简介")),
    ("schedule", ("时间线", "日程", "安排", "时间安排")),
    ("actions", ("你将看到", "本群内我们会", "需要做什么", "行动")),
)


def _clean_lines(source: str) -> List[str]:
    return [line.strip() for line in str(source or "").splitlines() if line.strip()]


def _hits(source: str, terms: Iterable[str]) -> List[str]:
    value = str(source or "").lower()
    return [term for term in terms if term.lower() in value]


def _explicit_heading(line: str) -> Optional[str]:
    original = re.sub(r"^#{1,4}\s*", "", line.strip())
    text = re.sub(r"^[【\[]|[】\]]$", "", original).strip().rstrip("：:")
    for key, names in _HEADING_MAP:
        if text in names or (original.rstrip().endswith(("：", ":")) and any(text.startswith(name) for name in names)):
            return key
    return None


def classify_content(source: str, explicit_mode: Optional[str] = None) -> Dict[str, Any]:
    """Classify copy into a layout mode with explainable confidence."""
    value = str(source or "")
    lines = _clean_lines(value)
    if explicit_mode:
        mode = str(explicit_mode).strip().lower()
        if mode not in MODES:
            raise ValueError(f"unsupported content mode: {explicit_mode}")
        return {
            "mode": mode,
            "confidence": 1.0,
            "reason": "用户显式指定内容模式",
            "signals": {"explicit_mode": True, "meeting_hits": [], "work_hits": [], "notice_hits": []},
            "recommended_sections": _recommended_sections(mode),
            "fold_default": mode in {"work_report", "meeting_summary", "long_summary"},
            "source_line_count": len(lines),
        }

    meeting_hits = _hits(value, _MEETING_TERMS)
    work_hits = _hits(value, _WORK_TERMS)
    notice_hits = _hits(value, _NOTICE_TERMS)
    dialogue_lines = sum(bool(re.search(r"(?:^|\n)\s*(?:[^：:]{1,16})[：:]\s+", line)) for line in lines)
    first_person = bool(re.search(r"(?:我(?:已|已经|完成|做了|负责|交付)|本周工作|本月工作)", value))
    long_signal = len(value.strip()) > 520 or len(lines) > 10

    meeting_score = len(set(meeting_hits)) + (2 if dialogue_lines >= 2 else 0)
    work_score = len(set(work_hits)) + (2 if first_person else 0)
    notice_score = len(set(notice_hits))
    if meeting_score >= 2 and meeting_score >= work_score:
        mode = "meeting_summary"
        reason = "检测到会议/沟通/纪要或多人发言结构"
        score = meeting_score
    elif work_score >= 2:
        mode = "work_report"
        reason = "检测到工作汇报、进展、完成/计划/风险等状态结构"
        score = work_score
    elif long_signal:
        mode = "long_summary"
        reason = "内容较长但没有足够强的会议或工作汇报信号，采用保守长文结构"
        score = 1
    else:
        mode = "notice"
        reason = "以通知/活动/说明为主，保留时间、行动和补充信息"
        score = max(notice_score, 1)

    confidence = 0.55 + min(0.35, score * 0.07)
    if meeting_score and work_score and abs(meeting_score - work_score) <= 1:
        confidence -= 0.12
        reason += "；会议与工作信号接近，分组仅作辅助建议"
    if mode == "long_summary" and not (meeting_score or work_score):
        confidence = 0.58
    return {
        "mode": mode,
        "confidence": round(max(0.45, min(confidence, 0.95)), 2),
        "reason": reason,
        "signals": {
            "explicit_mode": False,
            "meeting_hits": meeting_hits,
            "work_hits": work_hits,
            "notice_hits": notice_hits,
            "dialogue_line_count": dialogue_lines,
            "first_person": first_person,
            "long_signal": long_signal,
        },
        "recommended_sections": _recommended_sections(mode),
        "fold_default": mode in {"work_report", "meeting_summary", "long_summary"},
        "source_line_count": len(lines),
    }


def _recommended_sections(mode: str) -> List[str]:
    return {
        "meeting_summary": ["topics", "confirmed", "todo"],
        "work_report": ["overview", "completed", "in_progress", "next", "risks"],
        "long_summary": ["overview", "details", "actions"],
        "notice": ["intro", "schedule", "actions", "notes"],
    }.get(mode, ["details"])


def _bucket_for_line(line: str, mode: str, index: int) -> str:
    explicit = _explicit_heading(line)
    if explicit:
        return explicit
    lower = line.lower()
    if mode == "meeting_summary":
        if re.search(r"确认|同意|决定|定为|已开通|已完成|结论", line):
            return "confirmed"
        if re.search(r"待办|行动项|跟进|负责|下周|明天|需要|请|计划|后续", line):
            return "todo"
        return "topics" if index > 0 else "overview"
    if mode == "work_report":
        if re.search(r"已完成|完成了|做完|已交付|已上线|已通过|交付", line):
            return "completed"
        if re.search(r"进行中|推进中|开发中|测试中|待验收|还在|正在", line):
            return "in_progress"
        if re.search(r"下一步|接下来|下周|计划|准备|后续", line):
            return "next"
        if re.search(r"风险|卡点|问题是|依赖|需要支持|阻塞", line):
            return "risks"
        return "overview" if index == 0 else "details"
    if mode == "notice":
        if index == 0:
            return "intro"
        if re.search(r"时间线|日程|日期|\d{1,2}[月./-]\d{1,2}|\d{3,4}", line):
            return "schedule"
        if re.search(r"报名|提交|点击|领取|通知|会|需要|欢迎|培训|安排", line):
            return "actions"
        return "intro" if index <= 1 else "notes"
    return "overview" if index == 0 else "details"


def extract_structured_sections(source: str, mode: Optional[str] = None) -> Dict[str, Any]:
    """Group exact source lines for downstream layout and human review.

    No line is rewritten or dropped.  The ``items`` values are the exact
    source lines, and ``source_line`` is one-based within the non-empty view.
    """
    value = str(source or "")
    classification = classify_content(value, explicit_mode=mode)
    lines = _clean_lines(value)
    section_order = classification["recommended_sections"]
    buckets: Dict[str, List[Dict[str, Any]]] = {key: [] for key in section_order}
    buckets.setdefault("details", [])
    current: Optional[str] = None
    for index, line in enumerate(lines, start=1):
        explicit = _explicit_heading(line)
        if explicit:
            current = explicit
            buckets.setdefault(current, [])
            continue
        target = current or _bucket_for_line(line, classification["mode"], index - 1)
        buckets.setdefault(target, []).append({"text": line, "source_line": index})

    # Empty recommended sections are useful to consumers as a contract, but
    # the section list remains source-backed and is not rendered as invented
    # “待确认/暂无” copy.
    sections = [
        {
            "id": key,
            "label": _section_label(key),
            "items": items,
            "source_line_count": len(items),
        }
        for key, items in buckets.items()
        if items
    ]
    return {
        "mode": classification["mode"],
        "confidence": classification["confidence"],
        "reason": classification["reason"],
        "source_locked": True,
        "source_line_count": len(lines),
        "recommended_order": section_order,
        "sections": sections,
        "unassigned_source_lines": [
            index for index, line in enumerate(lines, start=1)
            if not any(item.get("source_line") == index for section in sections for item in section["items"])
        ],
    }


def _section_label(key: str) -> str:
    return {
        "topics": "讨论话题",
        "confirmed": "确认事项",
        "todo": "待办事项",
        "overview": "工作概述",
        "completed": "已完成",
        "in_progress": "进行中",
        "next": "下一步计划",
        "risks": "风险/卡点",
        "intro": "说明",
        "schedule": "时间安排",
        "actions": "行动与安排",
        "notes": "补充信息",
        "details": "详细信息",
    }.get(key, key)
