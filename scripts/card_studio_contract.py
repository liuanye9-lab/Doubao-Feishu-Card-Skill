#!/usr/bin/env python3
"""Shared contracts for the unified Feishu Card Studio pipeline.

The internal Card Studio patterns are intentionally represented here as small,
portable contracts rather than as a copy of any private skill package.  The
contracts make the handoff between intake (UX), compilation (RD), validation
(QA), and delivery observable in generated reports.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence


CONTRACT_VERSION = "doubao-feishu-card-studio-contract/1"
STABILITY_PROFILE = "stable-v1"


def build_stability_contract() -> Dict[str, Any]:
    """Return the fixed execution contract shared by every generated bundle.

    This is intentionally data, not a second planner.  Keeping the order and
    fallback rules in every report makes a later edit or remote delivery easy
    to audit and prevents callers from silently switching to an ad-hoc route.
    """
    return {
        "profile": STABILITY_PROFILE,
        "execution_order": [
            "lock_source_text",
            "resolve_input_brief",
            "resolve_scene",
            "resolve_scene_default_preset",
            "allocate_image_native_card_and_actions",
            "compile_raw_card_and_cardkit_wrapper",
            "run_structural_and_source_gates",
            "select_model_then_visual_review_if_required",
            "upload_real_img_key_and_recompile_if_required",
            "import_cardkit_and_readback_after_explicit_authorization_bot_preview_is_optional",
        ],
        "route_precedence": [
            "explicit_scene",
            "source_structure",
            "specific_keywords",
            "custom_fallback",
        ],
        "preset_precedence": [
            "explicit_preset",
            "registered_scene_default",
            "archetype_recommendation",
        ],
        "render_contract": "Card 2.0 stable native subset; raw card and CardKit wrapper share one final DSL",
        "action_contract": "native_card_only; real URL or implemented application-bot callback/form required",
        "image_contract": "Every card gets a direct model-generated visual by default: Seedream 5.0 Pro for static information or automatically selected Seedance 2.5 GIF for motion-worthy content; explicit no-image is the only no-visual fallback; no HTML conversion, local overlay, or post-processing",
        "fallback_contract": "preserve source and report the exact degraded field; never invent facts, URLs, img_keys, or remote evidence",
        "remote_delivery_contract": "one preflight and one confirmation for requested remote writes; import CardKit and read back evidence; Bot preview only if explicitly requested",
    }


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def build_input_brief(
    source_text: str,
    *,
    purpose: Optional[str] = None,
    recipient: Optional[str] = None,
    material_kind: str = "plain_text",
) -> Dict[str, Any]:
    """Describe the minimum natural-language intake without changing copy.

    ``source_text`` remains the canonical material.  Purpose and recipient are
    context for layout and delivery planning only; they must never silently
    become a send target or alter source facts.
    """
    source = str(source_text or "")
    purpose_value = _clean(purpose)
    recipient_value = _clean(recipient)
    kind = _clean(material_kind) or "plain_text"
    return {
        "schema": CONTRACT_VERSION,
        "minimum_input": ["material", "purpose", "recipient"],
        "material": {
            "kind": kind,
            "canonical_source": "source_text",
            "source_locked": True,
            "source_line_count": len(source.splitlines() or [source]),
            "structured_material_note": (
                "文档、表格或截图需先由调用方提取为可核验的 source_text；本地编排器不假装读取私有附件。"
                if kind != "plain_text"
                else "当前编排器以 UTF-8 文案作为唯一事实源。"
            ),
        },
        "purpose": {
            "value": purpose_value or None,
            "source": "user" if purpose_value else "not_provided",
            "role": "layout_and_content_context_only",
        },
        "recipient": {
            "value": recipient_value or None,
            "source": "user" if recipient_value else "not_provided",
            "role": "delivery_context_only",
        },
        "delivery_target_policy": (
            "recipient is descriptive context; a remote send target must be explicitly resolved and confirmed. "
            "Default Bot preview remains the current user, and a group send requires an explicit chat_id."
        ),
        "source_fidelity": "facts, URLs, dates, metrics, names, and quote text remain source-backed",
    }


def _gate(
    gate_id: str,
    *,
    status: str,
    severity: str,
    description: str,
    evidence: Optional[Mapping[str, Any]] = None,
    required: bool = True,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "id": gate_id,
        "status": status,
        "severity": severity,
        "required": required,
        "description": description,
    }
    if evidence:
        result["evidence"] = dict(evidence)
    return result


def _contains_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        lowered = value.lower()
        return (
            "${" in value
            or "example.com" in lowered
            or "replace_me" in lowered
            or "todo_" in lowered
            or "your_" in lowered
            or "_mock_" in lowered
            or lowered.startswith("mock_")
        )
    if isinstance(value, Mapping):
        return any(_contains_placeholder(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_placeholder(item) for item in value)
    return False


def build_quality_gates(
    card: Mapping[str, Any],
    spec: Mapping[str, Any],
    validation: Mapping[str, Any],
    *,
    wrapper: Optional[Mapping[str, Any]] = None,
    cardkit_valid: bool = False,
    scene_contract_ok: bool = True,
    image_required: bool = False,
    visual_output_ready: bool = True,
    image_ready: bool = True,
) -> Dict[str, Any]:
    """Build deterministic and manual-review quality gates for one bundle.

    The P0-P7 gates follow the stable Card Studio review vocabulary.  Visual
    contrast, semantic color, and whether the final bitmap accidentally looks
    like a button remain manual gates because a JSON report cannot inspect
    rendered pixels honestly.
    """
    analysis = spec.get("analysis") if isinstance(spec.get("analysis"), Mapping) else {}
    source_text = _clean(analysis.get("source_text"))
    header = card.get("header") if isinstance(card.get("header"), Mapping) else {}
    title = header.get("title") if isinstance(header.get("title"), Mapping) else {}
    config = card.get("config") if isinstance(card.get("config"), Mapping) else {}
    summary = config.get("summary") if isinstance(config.get("summary"), Mapping) else {}
    summary_content = _clean(summary.get("content"))
    body = card.get("body") if isinstance(card.get("body"), Mapping) else {}
    elements = body.get("elements") if isinstance(body.get("elements"), list) else []
    validation_ok = bool(validation.get("ok"))
    no_placeholders = not _contains_placeholder(card)
    source_locked = bool(analysis.get("source_locked")) and bool(analysis.get("source_sha256"))
    validation_stats = validation.get("stats") if isinstance(validation.get("stats"), Mapping) else {}
    visible_text_chars = int(validation_stats.get("visible_text_chars", 0) or 0)
    max_text_block_chars = int(validation_stats.get("max_text_block_chars", 0) or 0)
    emoji_count = int(validation_stats.get("emoji_count", 0) or 0)
    emoji_mode = str(spec.get("emoji_mode") or "semantic")
    visual_spec = spec.get("visual_spec") if isinstance(spec.get("visual_spec"), Mapping) else {}
    chart_plan = visual_spec.get("chart") if isinstance(visual_spec, Mapping) else None
    gates: List[Dict[str, Any]] = [
        _gate(
            "summary_contract",
            status=(
                "pass"
                if 8 <= len(summary_content) <= 60 and not _contains_placeholder(summary_content)
                else "blocked"
            ),
            severity="error",
            description="消息列表摘要为 8–60 个来源可追溯字符，不使用占位内容。",
            evidence={"content": summary_content, "length": len(summary_content)},
        ),
        _gate(
            "P0_intent_coverage",
            status="pass" if source_text and title.get("content") and elements else "blocked",
            severity="error",
            description="输入材料、卡片标题和至少一个内容单元可追溯。",
            evidence={"source_present": bool(source_text), "title_present": bool(title.get("content")), "element_count": len(elements)},
        ),
        _gate(
            "P1_hierarchy",
            status="pass" if title.get("content") else "blocked",
            severity="error",
            description="首屏有一个明确主标题，主次信息不依赖装饰图猜测。",
            evidence={"title": title.get("content"), "body_direction": body.get("direction")},
        ),
        _gate(
            "P2_grouping",
            status="pass" if isinstance(spec.get("blocks"), list) and spec.get("blocks") else "review",
            severity="error",
            description="内容按事实、关系、时间线或补充信息分组。",
            evidence={"spec_block_count": len(spec.get("blocks", [])) if isinstance(spec.get("blocks"), list) else 0},
        ),
        _gate(
            "P3_complexity",
            status="pass" if len(elements) <= 8 else "review",
            severity="warning",
            description="移动端首屏控制结构复杂度；过多组件需要人工确认是否折叠。",
            evidence={"top_level_element_count": len(elements), "recommended_range": "2-5 primary blocks; 8 is a review threshold"},
            required=False,
        ),
        _gate(
            "content_density",
            status="pass" if visible_text_chars <= 900 and max_text_block_chars <= 220 else "blocked",
            severity="error",
            description="可见卡片只保留一句摘要、3–5 个关键点、指标/图表和 CTA；完整原文留在 source.txt 或真实来源链接。",
            evidence={"visible_text_chars": visible_text_chars, "max_text_block_chars": max_text_block_chars, "limits": {"total": 900, "single_block": 220}},
        ),
        _gate(
            "semantic_emoji",
            status="pass" if emoji_mode != "semantic" or 1 <= emoji_count <= 8 else "blocked",
            severity="error",
            description="默认使用节制的语义 Emoji 建立模块扫读锚点，不向每句重复加图标。",
            evidence={"emoji_mode": emoji_mode, "visible_emoji_count": emoji_count, "recommended": "3-6; compact cards may use 1-2"},
        ),
        _gate(
            "visual_strategy",
            status="pass" if bool(visual_spec) and bool(visual_spec.get("image_required")) == bool(image_required) else "blocked",
            severity="error",
            description="每张卡片默认有一份可编辑 visual-spec 和图片任务；仅明确无图时跳过。",
            evidence={"visual_spec_present": bool(visual_spec), "visual_type": visual_spec.get("visual_type"), "image_required": image_required},
        ),
        _gate(
            "chart_grounding",
            status="pass" if not chart_plan or int(validation_stats.get("charts", 0) or 0) >= 1 else "blocked",
            severity="error",
            description="存在至少两个同口径真实数值时，生成来源锁定的 CardKit 图表；不混合单位，不编造值。",
            evidence={"chart_planned": bool(chart_plan), "chart_count": int(validation_stats.get("charts", 0) or 0)},
        ),
        _gate(
            "P4_contrast",
            status="manual_review" if image_required else "pass",
            severity="manual",
            description="检查最终渲染图与原生 Card 的文字、背景和边界对比度。",
            evidence={"image_required": image_required},
            required=False,
        ),
        _gate(
            "P5_alignment",
            status="pass" if validation_ok else "blocked",
            severity="error",
            description="结构校验通过，列宽、容器和元素对齐遵守稳定子集。",
            evidence={"validation_ok": validation_ok},
        ),
        _gate(
            "P6_semantic_color",
            status="manual_review" if image_required else "pass",
            severity="manual",
            description="颜色表达状态和层级，不把强调色误作可点击控件。",
            evidence={"image_required": image_required},
            required=False,
        ),
        _gate(
            "P7_robustness",
            status="pass" if validation_ok and no_placeholders and scene_contract_ok else "blocked",
            severity="error",
            description="Card JSON、场景契约和占位内容门禁全部通过。",
            evidence={"validation_ok": validation_ok, "no_placeholders": no_placeholders, "scene_contract_ok": scene_contract_ok},
        ),
        _gate(
            "source_lock",
            status="pass" if source_locked else "blocked",
            severity="error",
            description="完整源文案和哈希存在，渲染改写可回溯。",
            evidence={"source_locked": source_locked},
        ),
        _gate(
            "action_integrity",
            status="pass" if validation_ok else "blocked",
            severity="error",
            description="真实动作只能由原生 Card URL/callback/form 承载。",
            evidence={
                "button_count": (validation.get("stats") or {}).get("buttons", 0),
                "callback_count": (validation.get("stats") or {}).get("callbacks", 0),
            },
        ),
        _gate(
            "image_cta_separation",
            status="manual_review" if image_required else "pass",
            severity="manual",
            description="确认 PNG/GIF 内没有按钮、CTA 胶囊、链接样控件或可点击暗示；媒体不承载行为。",
            evidence={
                "image_required": image_required,
                "native_button_policy": "native_card_only",
                "post_processing": "none",
            },
            required=False,
        ),
        _gate(
            "cardkit_parity",
            status="pass" if cardkit_valid and isinstance(wrapper, Mapping) and wrapper.get("dsl") == card else "blocked",
            severity="error",
            description="网页导入文件与裸 Card 来自同一份 DSL，且 wrapper 校验通过。",
            evidence={"cardkit_valid": cardkit_valid, "wrapper_present": isinstance(wrapper, Mapping)},
        ),
        _gate(
            "image_readiness",
            status="pass" if not image_required or (visual_output_ready and image_ready) else "blocked",
            severity="error",
            description="视觉卡片具备 Seedream 5.0 Pro、Seedance 2.5 或真实图片溯源和真实 img_key；无图卡片不受此门影响。",
            evidence={"image_required": image_required, "visual_output_ready": visual_output_ready, "image_ready": image_ready, "render_strategy": spec.get("render_strategy")},
        ),
    ]
    required_gates = [item for item in gates if item.get("required")]
    required_passed = all(item.get("status") == "pass" for item in required_gates)
    structural_gates = [item for item in required_gates if item.get("id") != "image_readiness"]
    structural_passed = all(item.get("status") == "pass" for item in structural_gates)
    required_failures = [item["id"] for item in required_gates if item.get("status") != "pass"]
    structural_failures = [item["id"] for item in structural_gates if item.get("status") != "pass"]
    manual_pending = [item["id"] for item in gates if item.get("status") == "manual_review"]
    return {
        "schema": CONTRACT_VERSION,
        "model": "P0-P7_plus_source_action_delivery",
        "required_passed": required_passed,
        "structural_passed": structural_passed,
        "required_failures": required_failures,
        "structural_failures": structural_failures,
        "manual_review_pending": manual_pending,
        "gates": gates,
        "remote_write_policy": (
            "required gates must pass; manual image gates must be visually reviewed before remote writes"
        ),
    }


def build_generation_workflow(
    quality_gates: Mapping[str, Any],
    *,
    validation_ok: bool,
    scene_contract_ok: bool,
    image_required: bool,
    visual_output_ready: bool,
    image_ready: bool,
    cardkit_valid: bool,
) -> Dict[str, Any]:
    """Describe the UX -> RD -> QA handoff without claiming hidden automation."""
    qa_ok = bool(quality_gates.get("required_passed"))
    structural_ok = bool(quality_gates.get("structural_passed", qa_ok))
    qa_status = "passed" if qa_ok else "blocked"
    if not structural_ok:
        qa_status = "blocked"
    elif image_required and not (visual_output_ready and image_ready):
        qa_status = "needs_media"
    return {
        "schema": CONTRACT_VERSION,
        "model": "ux_rd_qa",
        "source_of_truth": ["source.txt", "spec.json"],
        "stages": [
            {
                "id": "ux",
                "status": "completed",
                "responsibility": "把材料、用途、对象和内容关系转成 input_brief / information_allocation / visual plan",
                "outputs": ["input_brief", "summary_structure", "information_allocation", "prompt_routing"],
            },
            {
                "id": "rd",
                "status": "completed" if validation_ok else "blocked",
                "responsibility": "按 Card 2.0 稳定子集编译 raw Card 与同源 CardKit wrapper",
                "outputs": ["spec.json", "card", "cardkit.card", "cardkit.json"],
                "evidence": {"validation_ok": validation_ok, "cardkit_valid": cardkit_valid, "scene_contract_ok": scene_contract_ok},
            },
            {
                "id": "qa",
                "status": qa_status,
                "responsibility": "运行结构、事实、动作、图片溯源和交付边界质量门",
                "outputs": ["quality_gates", "report.json"],
                "evidence": {
                    "required_gates_passed": qa_ok,
                    "manual_review_pending": list(quality_gates.get("manual_review_pending", [])),
                    "image_required": image_required,
                    "visual_output_ready": visual_output_ready,
                    "image_ready": image_ready,
                },
            },
        ],
        "repair_route": (
            "QA failure -> inspect gate evidence -> edit source/spec -> recompile both dialects -> rerun validation; "
            "do not silently patch the final Card or claim a remote send."
        ),
        "editor_fallback": "after a valid draft, use CardKit for 80% -> 100% visual refinement and export/revalidate the edited card",
    }
