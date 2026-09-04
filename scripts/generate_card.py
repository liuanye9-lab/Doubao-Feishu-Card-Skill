#!/usr/bin/env python3
"""Generate a deterministic, mobile-safe Feishu Card 2.0 payload.

The generator deliberately accepts a small, content-first spec. It only emits
Card 2.0 keys that this skill owns; image keys, URLs, and callback values are
never guessed. A missing hero image produces an asset plan beside the card so
the card can still be generated without pretending that an image exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from auto_layout import EMOJI_ALIASES, build_auto_spec, normalize_emoji_aliases
from generate_style import build_style_document, infer_style
from runtime_profile import default_image_mode, image_mode_config, image_runtime, supported_image_modes
from validate_card import is_placeholder, normalize_cardkit_text_color


INK = "grey"
GOLD = "yellow"
TYPE_LABELS = {
    "timeline": "PIONEER TIMELINE",
    "training": "PIONEER TRAINING",
    "story": "PIONEER STORY",
    "submission": "PIONEER SUBMISSION",
    "review": "PIONEER REVIEW",
    "finalists": "PIONEER FINALISTS",
    "launch": "PIONEER LAUNCH",
    "custom": "DONGFANG YUN",
}
THEME_HEADER_TEMPLATES = {
    "oriental": "grey",
    "ink": "grey",
    "paper": "grey",
    "warm": "orange",
    "success": "green",
    "warning": "yellow",
    "danger": "red",
    "calm": "blue",
}
PRESET_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "presets" / "preset-index.json"
SCENE_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "scenes" / "scene-index.json"
SUPPORTED_RAW_BLOCK_TAGS = {
    "column_set",
    "collapsible_panel",
    "div",
    "markdown",
    "img",
    "img_combination",
    "person",
    "person_list",
    "chart",
    "table",
    "audio",
    "hr",
    "button",
    "overflow",
    "form",
    "input",
    "select_static",
    "multi_select_static",
    "select_person",
    "multi_select_person",
    "date_picker",
    "picker_time",
    "picker_datetime",
    "select_img",
    "checker",
    "interactive_container",
}
FORBIDDEN_CALLBACK_KEYS = {
    "user_id",
    "open_id",
    "union_id",
    "tenant_key",
    "access_token",
    "refresh_token",
    "secret",
    "webhook",
}


def load_preset_registry() -> Dict[str, Any]:
    """Load the single source of truth for built-in visual presets."""
    try:
        registry = json.loads(PRESET_REGISTRY_PATH.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"preset registry is unavailable: {PRESET_REGISTRY_PATH}") from exc
    if not isinstance(registry, dict) or not isinstance(registry.get("presets"), list):
        raise ValueError("preset registry must contain a presets array")
    return registry


def load_scene_registry() -> Dict[str, Any]:
    """Load the single source of truth for event lifecycle scene templates."""
    try:
        registry = json.loads(SCENE_REGISTRY_PATH.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"scene registry is unavailable: {SCENE_REGISTRY_PATH}") from exc
    if not isinstance(registry, dict) or not isinstance(registry.get("scenes"), list):
        raise ValueError("scene registry must contain a scenes array")
    return registry


def resolve_scene(spec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Resolve an explicit event lifecycle scene, if one was selected."""
    requested = non_empty(spec.get("scene"))
    if not requested:
        return None
    registry = load_scene_registry()
    for item in registry.get("scenes", []):
        if isinstance(item, dict) and item.get("id") == requested:
            return item
    raise ValueError(f"unknown scene: {requested}")


def resolve_preset(spec: Dict[str, Any], scene: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Resolve an explicit preset, or the default when no legacy theme is set.

    ``theme`` remains a backwards-compatible header shortcut. A named ``preset``
    opts into the richer style registry; otherwise a scene can supply its
    recommended preset. Old specs with a legacy ``theme`` keep their existing
    Card 2.0 output.
    """
    requested = non_empty(spec.get("preset"))
    legacy_theme = non_empty(spec.get("theme"))
    if not requested and legacy_theme:
        return None

    registry = load_preset_registry()
    preset_id = requested or non_empty((scene or {}).get("default_preset")) or non_empty(registry.get("default"))
    for item in registry.get("presets", []):
        if isinstance(item, dict) and item.get("id") == preset_id:
            return item
    raise ValueError(f"unknown preset: {preset_id}")


def as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def compact_text(value: Any) -> str:
    return re.sub(r"\s+", " ", as_text(value)).strip()


def non_empty(value: Any) -> Optional[str]:
    text = as_text(value).strip()
    return text or None


def contains_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return is_placeholder(value)
    if isinstance(value, list):
        return any(contains_placeholder(item) for item in value)
    if isinstance(value, dict):
        return any(contains_placeholder(item) for item in value.values())
    return False


def element_id(prefix: str, index: int) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_]+", "_", prefix).strip("_").lower() or "element"
    suffix = f"_{index:02d}"
    return f"{clean[:20 - len(suffix)]}{suffix}"


def plain(content: Any, *, text_size: Optional[str] = None, text_color: Optional[str] = None) -> Dict[str, Any]:
    value: Dict[str, Any] = {"tag": "plain_text", "content": as_text(content)}
    if text_size:
        value["text_size"] = text_size
    normalized_color = normalize_cardkit_text_color(text_color)
    if normalized_color:
        value["text_color"] = normalized_color
    return value


def markdown(content: Any, *, text_size: Optional[str] = None, margin: str = "0px", eid: Optional[str] = None) -> Dict[str, Any]:
    value: Dict[str, Any] = {"tag": "markdown", "content": as_text(content), "margin": margin}
    if text_size:
        value["text_size"] = text_size
    if eid:
        value["element_id"] = eid
    return value


def div(content: Any, *, text_size: str = "notation", text_color: Optional[str] = None, margin: str = "0px", eid: Optional[str] = None) -> Dict[str, Any]:
    value: Dict[str, Any] = {"tag": "div", "text": plain(content, text_size=text_size, text_color=text_color), "margin": margin}
    if eid:
        value["element_id"] = eid
    return value


def bold_value(value: Any) -> str:
    text = as_text(value)
    if not text:
        return ""
    return text if "**" in text else f"**{text}**"


def fact_value_size(value: Any) -> str:
    text = compact_text(value)
    if len(text) <= 12 and re.search(r"\d|%|倍|万|人|项|天|小时", text):
        return "heading-3"
    return "heading-4"


def body_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(as_text(item) for item in value)
    return as_text(value)


def _summary_fragments(node: Any) -> Iterable[str]:
    """Yield rendered text that can safely seed a message-list summary."""
    if isinstance(node, dict):
        tag = node.get("tag")
        if tag in {"markdown", "lark_md", "plain_text"} and isinstance(node.get("content"), str):
            yield node["content"]
        if tag == "div" and isinstance(node.get("text"), dict):
            text = node["text"].get("content")
            if isinstance(text, str):
                yield text
        for key, value in node.items():
            if key not in {"content", "text"}:
                yield from _summary_fragments(value)
    elif isinstance(node, list):
        for item in node:
            yield from _summary_fragments(item)


def _summary_text(value: Any) -> str:
    """Remove presentation syntax while keeping the source-backed words."""
    text = compact_text(value)
    text = re.sub(r"https?://\S+", "", text, flags=re.I)
    text = re.sub(r"^#{1,6}\s*", "", text)
    text = re.sub(r"[*_`~]", "", text)
    return compact_text(text).strip("：:;；，,。.!！?？")


def build_card_summary(spec: Dict[str, Any], title: str, body: Sequence[Dict[str, Any]]) -> str:
    """Produce an 8-60 character, source-backed Card summary.

    CardKit and message lists expose ``config.summary.content`` before a user
    opens the card.  A short title alone is often not enough context, so a
    first meaningful rendered fact is appended without inventing a result.
    """
    explicit = _summary_text(spec.get("summary"))
    if explicit and not is_placeholder(explicit) and 8 <= len(explicit) <= 60:
        return explicit

    clean_title = _summary_text(title)
    fragments: List[str] = []
    for fragment in _summary_fragments(body):
        clean = _summary_text(fragment)
        if not clean or clean == clean_title or clean in fragments:
            continue
        fragments.append(clean)
    for fragment in fragments:
        candidate = "｜".join(part for part in (clean_title, fragment) if part)
        if len(candidate) >= 8:
            return candidate[:60].rstrip("｜，, ")
    if len(clean_title) >= 8:
        return clean_title[:60]
    source = spec.get("analysis", {}).get("source_text") if isinstance(spec.get("analysis"), dict) else ""
    source_summary = _summary_text(source)
    if source_summary:
        candidate = "｜".join(part for part in (clean_title, source_summary) if part)
        return candidate[:60].rstrip("｜，, ") or clean_title
    return clean_title


AUTO_HIGHLIGHT_RE = re.compile(
    r"(?:20\d{2}[年./-]\d{1,2}[月./-]\d{1,2}(?:日|号)?|\d{1,2}月\d{1,2}(?:日|号)?|\d{1,2}[./-]\d{1,2}|截止时间|截止|请务必|必须|报名|提交|开始|结束|查看|领取|确认|完成|下一步|今日|明天)"
)

# A highlight is a native Card 2.0 surface: one column inside a column_set
# with a restrained background token. It is intentionally not an HTML/CSS
# construct, so the same hierarchy survives CardKit import and Bot delivery.
HIGHLIGHT_SURFACES = {
    "neutral": "grey-50",
    "brand": "grey-100",
    "info": "blue-50",
    "success": "green-50",
    "warning": "yellow-50",
    "danger": "red-50",
}
HIGHLIGHT_ACCENTS = {
    "neutral": "grey",
    "brand": None,
    "info": "blue",
    "success": "green",
    "warning": "orange",
    "danger": "red",
}


def semantic_highlight(value: Any, enabled: bool = False) -> str:
    """Apply a very small, reviewable emphasis budget to auto-generated copy."""
    text = as_text(value)
    if not enabled or not text or "**" in text:
        return text
    matches = list(AUTO_HIGHLIGHT_RE.finditer(text))[:2]
    if not matches:
        return text
    spans: List[Tuple[int, int]] = []
    for match in matches:
        start, end = match.start(), match.end()
        if spans and start <= spans[-1][1] + 1:
            spans[-1] = (spans[-1][0], end)
        else:
            spans.append((start, end))
    result: List[str] = []
    cursor = 0
    for start, end in spans:
        result.append(text[cursor:start])
        result.append(f"**{text[start:end]}**")
        cursor = end
    result.append(text[cursor:])
    return "".join(result)


def highlight_element(
    block: Dict[str, Any],
    counter: List[int],
    *,
    accent: str = GOLD,
    surface_style: str = "grey-50",
    auto_emphasis: bool = False,
) -> Optional[Dict[str, Any]]:
    """Render a source-backed emphasis block with a native Card surface.

    ``highlight`` is a high-level DSL block, not a new Feishu tag. The
    compiler maps it to the stable ``column_set`` + ``column.background_style``
    subset, keeping text editable while making the information hierarchy
    visible in CardKit. At most one short label/title and one body are rendered;
    long supporting copy should remain a normal section or collapsible panel.
    """
    label = non_empty(block.get("label", block.get("eyebrow")))
    title = non_empty(block.get("title", block.get("heading")))
    content = block.get("content", block.get("body", block.get("text")))
    content_text = body_text(content).strip() if content is not None else ""
    if not any((label, title, content_text)):
        return None

    tone = as_text(block.get("tone", block.get("status", "neutral"))).strip().lower() or "neutral"
    if tone not in HIGHLIGHT_SURFACES:
        tone = "neutral"
    requested_surface = non_empty(block.get("background_style"))
    allowed_surfaces = set(HIGHLIGHT_SURFACES.values()) | {surface_style}
    highlight_surface = requested_surface if requested_surface in allowed_surfaces else HIGHLIGHT_SURFACES[tone]
    highlight_accent = non_empty(block.get("accent_color")) or HIGHLIGHT_ACCENTS[tone] or accent
    padding = non_empty(block.get("padding")) or "10px 12px"
    spacing = non_empty(block.get("vertical_spacing")) or "4px"

    counter[0] += 1
    inner: List[Dict[str, Any]] = []
    if label:
        inner.append(div(label, text_size="notation", text_color=highlight_accent, eid=element_id("highlight_label", counter[0])))
    if title:
        inner.append(
            markdown(
                title if "**" in title else f"**{title}**",
                text_size=non_empty(block.get("title_size")) or "heading-4",
                eid=element_id("highlight_title", counter[0]),
            )
        )
    if content_text:
        inner.append(
            markdown(
                semantic_highlight(content_text, auto_emphasis),
                text_size=non_empty(block.get("text_size")) or "normal_v2",
                eid=element_id("highlight_body", counter[0]),
            )
        )

    return {
        "tag": "column_set",
        "flex_mode": "none",
        "horizontal_spacing": "0px",
        "margin": non_empty(block.get("margin")) or "0px",
        "element_id": element_id("highlight", counter[0]),
        "columns": [
            {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "background_style": highlight_surface,
                "padding": padding,
                "vertical_spacing": spacing,
                "elements": inner,
            }
        ],
    }


def section_elements(
    spec: Dict[str, Any],
    counter: List[int],
    field: str = "sections",
    *,
    accent: str = GOLD,
    surface_style: str = "grey-50",
    auto_emphasis: bool = False,
) -> List[Dict[str, Any]]:
    elements: List[Dict[str, Any]] = []
    for section in spec.get(field, []) or []:
        if not isinstance(section, dict):
            continue
        if section.get("highlight") or section.get("highlighted"):
            highlight = highlight_element(
                section,
                counter,
                accent=accent,
                surface_style=surface_style,
                auto_emphasis=auto_emphasis,
            )
            if highlight:
                elements.append(highlight)
            continue
        title = non_empty(section.get("title"))
        if title:
            counter[0] += 1
            elements.append(markdown(f"**{title}**", text_size="heading-4", eid=element_id("section_title", counter[0])))
        content = section.get("body", section.get("content"))
        if content is None and section.get("items") is not None:
            items = section.get("items")
            content = "\n".join(f"- {as_text(item)}" for item in items) if isinstance(items, list) else items
        if content is not None and as_text(content).strip():
            counter[0] += 1
            elements.append(markdown(semantic_highlight(body_text(content), auto_emphasis), text_size=section.get("text_size", "normal_v2"), eid=element_id("section_body", counter[0])))
    return elements


def block_element_id(block: Dict[str, Any], prefix: str, counter: List[int]) -> Optional[str]:
    """Return a user-stable id for a block, or a generated id when needed."""
    requested = non_empty(block.get("element_id", block.get("id")))
    if requested:
        clean = re.sub(r"[^a-zA-Z0-9_]+", "_", requested).strip("_")
        if clean and clean[0].isalpha():
            return clean[:20]
    counter[0] += 1
    return element_id(prefix, counter[0])


def table_element(block: Dict[str, Any], counter: List[int]) -> Dict[str, Any]:
    """Compile a small declarative table block into the Card 2.0 table shape."""
    raw_columns = block.get("columns") or []
    if not isinstance(raw_columns, list) or not raw_columns:
        raise ValueError("table block needs a non-empty columns array")
    columns: List[Dict[str, Any]] = []
    for index, column in enumerate(raw_columns, start=1):
        if isinstance(column, str):
            display_name = column.strip() or f"列 {index}"
            name = re.sub(r"[^a-zA-Z0-9_]+", "_", display_name).strip("_").lower() or f"column_{index}"
            if not name[0].isalpha():
                name = f"column_{name}"
            columns.append({"name": name[:32], "display_name": display_name, "data_type": "text", "width": "auto"})
            continue
        if not isinstance(column, dict):
            raise ValueError(f"table column {index} must be a string or object")
        item = dict(column)
        name = non_empty(item.get("name")) or f"column_{index}"
        display_name = non_empty(item.get("display_name", item.get("label"))) or name
        item["name"] = name
        item["display_name"] = display_name
        item.setdefault("data_type", "text")
        columns.append(item)

    raw_rows = block.get("rows") or []
    if not isinstance(raw_rows, list):
        raise ValueError("table block rows must be an array")
    names = [column["name"] for column in columns]
    rows: List[Dict[str, Any]] = []
    for row in raw_rows:
        if isinstance(row, dict):
            rows.append(dict(row))
        elif isinstance(row, list):
            rows.append({name: value for name, value in zip(names, row)})
        else:
            raise ValueError("table rows must contain objects or arrays")

    table: Dict[str, Any] = {
        "tag": "table",
        "element_id": block_element_id(block, "table", counter),
        "columns": columns,
        "rows": rows,
        "page_size": int(block.get("page_size", 5)),
        "row_height": block.get("row_height", "auto"),
    }
    if block.get("row_max_height") is not None:
        table["row_max_height"] = block["row_max_height"]
    if isinstance(block.get("header_style"), dict):
        table["header_style"] = dict(block["header_style"])
    return table


def chart_element(block: Dict[str, Any], counter: List[int]) -> Dict[str, Any]:
    chart_spec = block.get("chart_spec", block.get("spec"))
    if not isinstance(chart_spec, dict):
        raise ValueError("chart block needs a chart_spec object")
    chart: Dict[str, Any] = {
        "tag": "chart",
        "element_id": block_element_id(block, "chart", counter),
        "chart_spec": chart_spec,
    }
    for key in ("aspect_ratio", "color_theme", "preview", "height"):
        if key in block:
            chart[key] = block[key]
    return chart


def image_block_element(block: Dict[str, Any], counter: List[int]) -> Optional[Dict[str, Any]]:
    img_key = non_empty(block.get("img_key", block.get("image_key")))
    if not img_key:
        return None
    return {
        "tag": "img",
        "img_key": img_key,
        "alt": plain(non_empty(block.get("alt")) or "飞书 AI 先锋卡片图片"),
        "scale_type": block.get("scale_type", "crop_center"),
        "size": block.get("size", "stretch"),
        "corner_radius": block.get("corner_radius", "8px"),
        "preview": block.get("preview", True),
        "margin": block.get("margin", "0px"),
        "element_id": block_element_id(block, "image", counter),
    }


def default_combination_mode(image_count: int) -> str:
    if image_count == 2:
        return "double"
    if image_count == 3:
        return "triple"
    if image_count <= 6:
        return "bisect"
    return "trisect"


def image_combination_element(block: Dict[str, Any], counter: List[int]) -> Dict[str, Any]:
    """Compile a small multi-image strip from real uploaded image keys."""
    raw_images = block.get("img_list", block.get("images", []))
    if not isinstance(raw_images, list) or not raw_images:
        raise ValueError("image_combination block needs a non-empty images array")
    images: List[Dict[str, Any]] = []
    for index, item in enumerate(raw_images, start=1):
        if isinstance(item, str):
            img_key = non_empty(item)
            image = {"img_key": img_key, "alt": plain(f"卡片图片 {index}"), "preview": True}
        elif isinstance(item, dict):
            image = dict(item)
            img_key = non_empty(image.get("img_key", image.get("image_key")))
            image["img_key"] = img_key
            alt = image.get("alt")
            image["alt"] = plain(alt or f"卡片图片 {index}") if isinstance(alt, str) or alt is None else alt
            image.setdefault("preview", True)
        else:
            raise ValueError("image_combination images must contain strings or objects")
        if not img_key:
            raise ValueError(f"image_combination image {index} is missing img_key")
        images.append(image)
    mode = non_empty(block.get("combination_mode")) or default_combination_mode(len(images))
    limits = {"double": 2, "triple": 3, "bisect": 6, "trisect": 9}
    if mode not in limits:
        raise ValueError(f"unsupported image_combination mode: {mode}")
    if len(images) > limits[mode]:
        raise ValueError(f"image_combination mode {mode} supports at most {limits[mode]} images")
    return {
        "tag": "img_combination",
        "combination_mode": mode,
        "img_list": images,
        "margin": block.get("margin", "0px"),
        "element_id": block_element_id(block, "image_combo", counter),
    }


def media_switcher_elements(
    block: Dict[str, Any],
    counter: List[int],
    *,
    accent: str = GOLD,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Compile a callback-driven image switcher.

    Feishu Card 2.0 does not provide a generic client-side image carousel. A
    switcher is therefore an application-bot contract: the current image is
    rendered as a normal ``img`` and each tab asks the backend to replace that
    image with the selected item's real ``img_key``. The first/current image
    remains the static fallback when callbacks are unavailable.
    """
    raw_items = block.get("items", block.get("images", []))
    if not isinstance(raw_items, list) or not 2 <= len(raw_items) <= 4:
        raise ValueError("media_switcher needs 2 to 4 image items")
    items: List[Dict[str, Any]] = []
    for index, raw_item in enumerate(raw_items, start=1):
        if not isinstance(raw_item, dict):
            raise ValueError("media_switcher items must be objects")
        item = dict(raw_item)
        image_key = non_empty(item.get("img_key", item.get("image_key")))
        if not image_key:
            raise ValueError(f"media_switcher item {index} needs a real img_key")
        item["img_key"] = image_key
        item_id = non_empty(item.get("id")) or f"media_{index}"
        label = non_empty(item.get("label", item.get("title"))) or f"图片 {index}"
        item["id"] = item_id
        item["label"] = label
        items.append(item)

    raw_active = block.get("active_index", 0)
    try:
        active_index = int(raw_active)
    except (TypeError, ValueError) as exc:
        raise ValueError("media_switcher active_index must be an integer") from exc
    if not 0 <= active_index < len(items):
        raise ValueError("media_switcher active_index is outside the items array")

    active = items[active_index]
    image = image_block_element(
        {
            **active,
            "alt": active.get("alt") or f"{active['label']}图片",
            "size": block.get("size", "stretch"),
            "scale_type": block.get("scale_type", "crop_center"),
            "corner_radius": block.get("corner_radius", "8px"),
            "preview": block.get("preview", True),
            "margin": block.get("margin", "0px"),
        },
        counter,
    )
    if image is None:
        raise ValueError("media_switcher active item has no image")

    media_id = non_empty(block.get("id")) or "media_switcher"
    callback_action = non_empty(block.get("callback_action")) or "switch_media"
    button_specs: List[Dict[str, Any]] = []
    for index, item in enumerate(items):
        button_specs.append(
            {
                "text": item["label"],
                "style": "primary" if index == active_index else "secondary",
                "callback": {
                    "action": callback_action,
                    "handler": block.get("handler", "application backend"),
                    "permission_mode": block.get("permission_mode", "server_authorized"),
                    "required_capabilities": block.get("required_capabilities", ["card.action.trigger", "card.update"]),
                    "value": {
                        "media_id": media_id,
                        "target_id": item["id"],
                        "target_index": index,
                        "state": "media_selected",
                    },
                },
            }
        )
    buttons, contracts = button_elements({"buttons": button_specs}, counter, source_tag="media_switcher")

    label = div(
        f"当前图片：{active['label']}",
        text_size="notation",
        text_color=accent,
        eid=element_id("media_current", counter[0] + 1),
    )
    rows: List[Dict[str, Any]] = []
    for start in range(0, len(buttons), 2):
        row_buttons = buttons[start : start + 2]
        columns = [
            {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "padding": "0px",
                "vertical_align": "center",
                "elements": [button],
            }
            for button in row_buttons
        ]
        rows.append(
            {
                "tag": "column_set",
                "flex_mode": "bisect" if len(columns) == 2 else "none",
                "horizontal_spacing": "8px",
                "margin": "0px",
                "columns": columns,
                "element_id": element_id("media_switch_row", counter[0] + start + 1),
            }
        )
    return [image, label, *rows], contracts


def normalize_select_options(options: Any) -> List[Dict[str, Any]]:
    if not isinstance(options, list):
        return []
    result: List[Dict[str, Any]] = []
    for index, option in enumerate(options, start=1):
        if isinstance(option, str):
            result.append({"text": plain(option), "value": option})
        elif isinstance(option, dict):
            item = dict(option)
            text = item.get("text", item.get("label"))
            if isinstance(text, str):
                item["text"] = plain(text)
            elif not isinstance(text, dict):
                item["text"] = plain(f"选项 {index}")
            item.setdefault("value", str(index))
            result.append(item)
    return result


def native_block_element(block: Dict[str, Any], counter: List[int], kind: str) -> Dict[str, Any]:
    """Compile stable Card 2.0 leaf components without guessing tenant data."""
    tag = kind
    element: Dict[str, Any] = {"tag": tag}
    if tag == "person":
        user_id = non_empty(block.get("user_id", block.get("id")))
        if not user_id:
            raise ValueError("person block needs user_id")
        element["user_id"] = user_id
        for key in ("size", "show_avatar", "show_name", "style"):
            if key in block:
                element[key] = block[key]
    elif tag == "person_list":
        people = block.get("persons", block.get("user_ids", []))
        if not isinstance(people, list) or not people:
            raise ValueError("person_list block needs a non-empty persons array")
        element["persons"] = [
            ({"id": item} if isinstance(item, str) else dict(item))
            for item in people if isinstance(item, (str, dict))
        ]
        if not element["persons"]:
            raise ValueError("person_list persons must contain IDs or objects")
        for key in ("size", "show_name", "show_avatar", "max_display_count"):
            if key in block:
                element[key] = block[key]
    elif tag == "overflow":
        options = normalize_select_options(block.get("options", []))
        if not options:
            raise ValueError("overflow block needs a non-empty options array")
        element["options"] = options
    elif tag in {"input", "select_static", "multi_select_static", "select_person", "multi_select_person", "date_picker", "picker_time", "picker_datetime", "checker"}:
        name = non_empty(block.get("name"))
        if not name:
            raise ValueError(f"{tag} block needs name")
        element["name"] = name
        if tag in {"select_static", "multi_select_static"}:
            options = normalize_select_options(block.get("options", []))
            if not options:
                raise ValueError(f"{tag} block needs a non-empty options array")
            element["options"] = options
        for key in (
            "required", "disabled", "disabled_tips", "default_value", "initial_option",
            "initial_options", "initial_date", "initial_time", "initial_datetime",
            "max_length", "input_type", "rows", "resize", "width", "label", "checked",
        ):
            if key in block:
                element[key] = block[key]
        if "placeholder" in block:
            value = block["placeholder"]
            element["placeholder"] = plain(value) if isinstance(value, str) else value
        if tag == "checker" and "text" in block:
            value = block["text"]
            element["text"] = plain(value) if isinstance(value, str) else value
    else:
        raise ValueError(f"unsupported native component: {tag}")
    if tag not in {"person", "person_list"} or block.get("element_id"):
        element["element_id"] = block_element_id(block, tag, counter)
    for key in ("behaviors", "confirm", "hover_tips", "margin"):
        if key in block:
            element[key] = block[key]
    return element


def interactive_container_element(
    block: Dict[str, Any], counter: List[int], *, accent: str, surface_style: str, auto_emphasis: bool
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    inner, contracts = block_elements(
        block.get("blocks", block.get("elements", [])), counter,
        accent=accent, surface_style=surface_style, auto_emphasis=auto_emphasis,
    )
    if not inner:
        raise ValueError("interactive_container block needs non-empty blocks")

    def contains_forbidden_container(node: Any) -> bool:
        if isinstance(node, list):
            return any(contains_forbidden_container(item) for item in node)
        if not isinstance(node, dict):
            return False
        if node.get("tag") in {"form", "table"}:
            return True
        return any(contains_forbidden_container(value) for value in node.values())

    if contains_forbidden_container(inner):
        raise ValueError("interactive_container cannot contain form or table")

    action_source = dict(block)
    raw_behaviors = block.get("behaviors")
    if "url" not in action_source and "callback" not in action_source:
        if not isinstance(raw_behaviors, list) or len(raw_behaviors) != 1 or not isinstance(raw_behaviors[0], dict):
            raise ValueError("interactive_container block needs exactly one behavior")
        raw_behavior = raw_behaviors[0]
        if raw_behavior.get("type") == "open_url":
            action_source["url"] = raw_behavior.get("default_url")
        elif raw_behavior.get("type") == "callback":
            value = raw_behavior.get("value")
            if isinstance(value, dict):
                action_source["callback"] = {"action": value.get("action"), "value": {key: item for key, item in value.items() if key != "action"}}
            else:
                action_source["callback"] = value
        else:
            raise ValueError("interactive_container behavior must be callback or open_url")
    behavior, contract = action_behavior(action_source, 1, non_empty(block.get("label")) or "interactive_container", "interactive_container")
    if contract:
        contracts.append(contract)
    legacy_border = block.get("border")
    has_border = block.get("has_border")
    border_color = block.get("border_color")
    if legacy_border is not None:
        has_border = True if has_border is None else has_border
        if border_color is None and isinstance(legacy_border, dict):
            border_color = legacy_border.get("color")
    element: Dict[str, Any] = {
        "tag": "interactive_container",
        "elements": inner,
        "behaviors": [behavior],
        "element_id": block_element_id(block, "interactive", counter),
    }
    if has_border is not None:
        element["has_border"] = bool(has_border)
    if border_color is not None:
        element["border_color"] = border_color
    for key in ("disabled", "disabled_tips", "hover_tips", "background_style", "padding", "margin"):
        if key in block:
            element[key] = block[key]
    return element, contracts


def form_element(block: Dict[str, Any], counter: List[int]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Compile the common input/select/date form path without hiding the raw escape hatch."""
    form_name = non_empty(block.get("name")) or "card_form"
    form_elements: List[Dict[str, Any]] = []
    contracts: List[Dict[str, Any]] = []
    items = block.get("items", block.get("elements", [])) or []
    if not isinstance(items, list):
        raise ValueError("form block items must be an array")
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        kind = as_text(item.get("type", item.get("tag", "input"))).lower()
        if kind in {"text", "markdown"}:
            form_elements.append(markdown(item.get("content", item.get("text", "")), text_size=item.get("text_size")))
            continue
        if kind in {"button", "submit", "reset"}:
            form_item = dict(item)
            if kind == "submit":
                form_item["action_type"] = "form_submit"
            elif kind == "reset":
                form_item["action_type"] = "form_reset"
            if form_item.get("action_type") == "form_reset" and not form_item.get("url") and form_item.get("callback") is None:
                button = {
                    "tag": "button",
                    "name": non_empty(form_item.get("name")) or f"reset_{index}",
                    "action_type": "form_reset",
                    "text": plain(non_empty(form_item.get("text", form_item.get("label"))) or "重置"),
                    "type": "default",
                    "width": form_item.get("width", "fill"),
                    "element_id": block_element_id(form_item, "form_button", counter),
                }
            else:
                buttons, button_contracts = button_elements({"buttons": [form_item]}, counter)
                if not buttons:
                    continue
                button = buttons[0]
                button["name"] = non_empty(form_item.get("name")) or f"button_{index}"
                if form_item.get("action_type"):
                    button["action_type"] = form_item["action_type"]
                contracts.extend(button_contracts)
            form_elements.append(button)
            continue

        tag = {
            "input": "input",
            "select": "select_static",
            "select_static": "select_static",
            "multi_select": "multi_select_static",
            "multi_select_static": "multi_select_static",
            "date": "date_picker",
            "date_picker": "date_picker",
            "time": "picker_time",
            "picker_time": "picker_time",
            "datetime": "picker_datetime",
            "picker_datetime": "picker_datetime",
            "select_person": "select_person",
            "multi_select_person": "multi_select_person",
            "checker": "checker",
        }.get(kind)
        if tag is None:
            raw = item.get("element") if isinstance(item.get("element"), dict) else item
            if isinstance(raw, dict) and raw.get("tag") in SUPPORTED_RAW_BLOCK_TAGS:
                form_elements.append(dict(raw))
            continue
        element: Dict[str, Any] = {
            "tag": tag,
            "name": non_empty(item.get("name")) or f"field_{index}",
            "width": item.get("width", "fill"),
        }
        for key in ("required", "disabled", "disabled_tips", "placeholder", "default_value", "initial_date", "initial_time", "initial_datetime", "max_length", "input_type", "rows", "resize", "label"):
            if key in item:
                value = item[key]
                if key == "placeholder" and isinstance(value, str):
                    value = plain(value)
                element[key] = value
        if tag in {"select_static", "multi_select_static"}:
            element["options"] = normalize_select_options(item.get("options", []))
        if tag == "checker" and "text" in item:
            element["text"] = plain(item["text"]) if isinstance(item["text"], str) else item["text"]
        form_elements.append(element)

    form: Dict[str, Any] = {
        "tag": "form",
        "name": form_name,
        "direction": block.get("direction", "vertical"),
        "vertical_spacing": block.get("vertical_spacing", "8px"),
        "elements": form_elements,
        "element_id": block_element_id(block, "form", counter),
    }
    return form, contracts


def default_flex_mode(column_count: int) -> str:
    if column_count <= 1:
        return "none"
    if column_count == 2:
        return "bisect"
    if column_count == 3:
        return "trisect"
    return "stretch"


def block_elements(
    blocks: Any,
    counter: List[int],
    *,
    accent: str = GOLD,
    surface_style: str = "grey-50",
    auto_emphasis: bool = False,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Render the low-barrier explicit block DSL while keeping raw JSON available."""
    if not isinstance(blocks, list):
        raise ValueError("blocks must be an array")
    elements: List[Dict[str, Any]] = []
    contracts: List[Dict[str, Any]] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        kind = as_text(block.get("type", block.get("kind", "markdown"))).lower()
        if kind in {"text", "markdown", "heading"}:
            text_size = block.get("text_size") or ("heading" if kind == "heading" else "normal_v2")
            elements.append(markdown(semantic_highlight(block.get("content", block.get("text", "")), auto_emphasis), text_size=text_size, eid=block_element_id(block, "text", counter)))
        elif kind in {"highlight", "callout"}:
            highlight = highlight_element(
                block,
                counter,
                accent=accent,
                surface_style=surface_style,
                auto_emphasis=auto_emphasis,
            )
            if highlight:
                elements.append(highlight)
        elif kind == "div":
            elements.append(div(block.get("content", block.get("text", "")), text_size=block.get("text_size", "notation"), text_color=block.get("text_color"), eid=block_element_id(block, "div", counter)))
        elif kind == "section":
            if block.get("highlight") or block.get("highlighted"):
                highlight = highlight_element(
                    block,
                    counter,
                    accent=accent,
                    surface_style=surface_style,
                    auto_emphasis=auto_emphasis,
                )
                if highlight:
                    elements.append(highlight)
            else:
                elements.extend(
                    section_elements(
                        {"sections": [block]},
                        counter,
                        accent=accent,
                        surface_style=surface_style,
                        auto_emphasis=auto_emphasis,
                    )
                )
        elif kind in {"facts", "metrics"}:
            items = block.get("items", block.get("facts", block.get("metrics", [])))
            if kind == "metrics":
                items = [{"label": item.get("metric", item.get("label", "")), "value": item.get("value", "")} if isinstance(item, dict) else item for item in (items or [])]
            elements.extend(fact_elements({"facts": items}, counter, accent=accent, surface_style=surface_style))
        elif kind == "timeline":
            timeline_spec = {
                "timeline": block.get("items", block.get("timeline", [])),
                "timeline_title": block.get("title", block.get("timeline_title")),
                "timeline_focus": block.get("timeline_focus", False),
                "timeline_date_size": block.get("timeline_date_size"),
                "timeline_date_bold": block.get("timeline_date_bold", False),
                "show_title": block.get("show_title", True),
                "emoji_mode": block.get("emoji_mode", "auto"),
            }
            elements.extend(timeline_elements(timeline_spec, counter, accent=accent, surface_style=surface_style, auto_emphasis=auto_emphasis))
        elif kind == "quote":
            quote = quote_element({"quote": block}, counter, accent=accent, surface_style=surface_style)
            if quote:
                elements.append(quote)
        elif kind in {"button", "buttons"}:
            buttons = block.get("items", block.get("buttons", [block] if kind == "button" else []))
            button_elements_result, button_contracts = button_elements({"buttons": buttons}, counter)
            elements.extend(button_elements_result)
            contracts.extend(button_contracts)
        elif kind in {"image", "gif", "animated_image", "motion_image"}:
            image = image_block_element(block, counter)
            if image:
                elements.append(image)
        elif kind in {"image_combination", "image_group", "gallery"}:
            elements.append(image_combination_element(block, counter))
        elif kind in {"media_switcher", "image_switcher", "image_carousel"}:
            switcher_elements, switcher_contracts = media_switcher_elements(block, counter, accent=accent)
            elements.extend(switcher_elements)
            contracts.extend(switcher_contracts)
        elif kind in {"divider", "hr"}:
            elements.append({"tag": "hr", "margin": block.get("margin", "0px"), "element_id": block_element_id(block, "divider", counter)})
        elif kind in {"person", "person_list", "input", "overflow", "select_static", "multi_select_static", "select_person", "multi_select_person", "date_picker", "picker_time", "picker_datetime", "checker"}:
            elements.append(native_block_element(block, counter, kind))
        elif kind == "interactive_container":
            container, container_contracts = interactive_container_element(
                block, counter, accent=accent, surface_style=surface_style, auto_emphasis=auto_emphasis
            )
            elements.append(container)
            contracts.extend(container_contracts)
        elif kind == "table":
            elements.append(table_element(block, counter))
        elif kind == "chart":
            elements.append(chart_element(block, counter))
        elif kind in {"collapse", "collapsible_panel"}:
            inner, inner_contracts = block_elements(
                block.get("blocks", block.get("elements", [])),
                counter,
                accent=accent,
                surface_style=surface_style,
                auto_emphasis=auto_emphasis,
            )
            elements.append(
                collapsible_panel(
                    non_empty(block.get("title")) or "展开详情",
                    inner,
                    counter,
                    surface_style=surface_style,
                )
            )
            contracts.extend(inner_contracts)
        elif kind in {"columns", "column_set"}:
            columns: List[Dict[str, Any]] = []
            for index, column in enumerate(block.get("columns", []) or [], start=1):
                if not isinstance(column, dict):
                    continue
                inner, inner_contracts = block_elements(
                    column.get("blocks", column.get("elements", [])),
                    counter,
                    accent=accent,
                    surface_style=surface_style,
                )
                contracts.extend(inner_contracts)
                columns.append({
                    "tag": "column",
                    "width": column.get("width", "weighted"),
                    "weight": column.get("weight", 1),
                    "vertical_align": column.get("vertical_align", "top"),
                    "padding": column.get("padding", "8px"),
                    "elements": inner,
                })
            if columns:
                elements.append({
                    "tag": "column_set",
                    "flex_mode": block.get("flex_mode") or default_flex_mode(len(columns)),
                    "horizontal_spacing": block.get("horizontal_spacing", "8px"),
                    "columns": columns,
                    "element_id": block_element_id(block, "columns", counter),
                })
        elif kind == "form":
            form, form_contracts = form_element(block, counter)
            elements.append(form)
            contracts.extend(form_contracts)
        elif kind in {"raw", "component"}:
            raw = block.get("element", block.get("value"))
            if not isinstance(raw, dict) or raw.get("tag") not in SUPPORTED_RAW_BLOCK_TAGS:
                raise ValueError("raw block needs a supported Feishu component in element")
            elements.append(dict(raw))
        else:
            raise ValueError(f"unsupported block type: {kind}")
    return elements, contracts


def fact_elements(
    spec: Dict[str, Any],
    counter: List[int],
    *,
    accent: str = GOLD,
    surface_style: str = "grey-50",
) -> List[Dict[str, Any]]:
    facts = [fact for fact in (spec.get("facts", []) or []) if isinstance(fact, dict)]
    if not facts:
        return []

    short = len(facts) <= 3 and all(len(compact_text(fact.get("label"))) <= 12 and len(compact_text(fact.get("value"))) <= 16 for fact in facts)
    if short:
        columns: List[Dict[str, Any]] = []
        for fact in facts:
            counter[0] += 1
            label = non_empty(fact.get("label")) or ""
            value = non_empty(fact.get("value")) or ""
            columns.append(
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "background_style": surface_style,
                    "padding": "8px",
                    "vertical_spacing": "4px",
                    "elements": [
                        div(label, text_size="notation", text_color=accent, eid=element_id("fact_label", counter[0])),
                        markdown(bold_value(value), text_size=fact_value_size(value), eid=element_id("fact_value", counter[0])),
                    ],
                }
            )
        counter[0] += 1
        return [
            {
                "tag": "column_set",
                "flex_mode": "trisect" if len(columns) == 3 else ("bisect" if len(columns) == 2 else "none"),
                "horizontal_spacing": "12px",
                "margin": "0px",
                "element_id": element_id("facts", counter[0]),
                "columns": columns,
            }
        ]

    # Four or more facts used to degrade into a flat sequence of label/value
    # pairs. Keep the same source values, but group them into at most two
    # columns per row so metadata reads as a compact block on mobile.
    elements: List[Dict[str, Any]] = []
    for start in range(0, len(facts), 2):
        row = facts[start : start + 2]
        columns: List[Dict[str, Any]] = []
        for fact in row:
            counter[0] += 1
            label = non_empty(fact.get("label")) or ""
            value = non_empty(fact.get("value")) or ""
            columns.append(
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "background_style": surface_style,
                    "padding": "8px",
                    "vertical_spacing": "4px",
                    "elements": [
                        div(label, text_size="notation", text_color=accent, eid=element_id("fact_label", counter[0])),
                        markdown(bold_value(value), text_size=fact_value_size(value), eid=element_id("fact_value", counter[0])),
                    ],
                }
            )
        counter[0] += 1
        elements.append(
            {
                "tag": "column_set",
                "flex_mode": "bisect" if len(columns) == 2 else "none",
                "horizontal_spacing": "12px",
                "margin": "0px",
                "element_id": element_id("facts", counter[0]),
                "columns": columns,
            }
        )
    return elements


def timeline_elements(
    spec: Dict[str, Any],
    counter: List[int],
    *,
    accent: str = GOLD,
    surface_style: str = "grey-50",
    auto_emphasis: bool = False,
) -> List[Dict[str, Any]]:
    milestones = [item for item in (spec.get("timeline", []) or []) if isinstance(item, dict)]
    if not milestones:
        return []
    focus = bool(spec.get("timeline_focus"))
    date_size = non_empty(spec.get("timeline_date_size")) or "heading-4"
    title_size = non_empty(spec.get("timeline_title_size")) or ("heading-3" if focus else "heading-4")
    date_bold = bool(spec.get("timeline_date_bold"))
    elements: List[Dict[str, Any]] = []
    if spec.get("show_title", True):
        counter[0] += 1
        heading = non_empty(spec.get("timeline_title")) or "PIONEER TIMELINE / 时间线"
        elements.append(
            markdown(
                f"**{heading}**",
                text_size="heading-3" if focus else None,
                eid=element_id("timeline_heading", counter[0]),
            )
        )
    emoji_mode = as_text(spec.get("emoji_mode", "auto"))
    for milestone_index, item in enumerate(milestones):
        counter[0] += 1
        row_number = counter[0]
        date = non_empty(item.get("date")) or ""
        title = non_empty(item.get("title"))
        content = body_text(item.get("body", item.get("content", ""))).strip()
        # Dates already carry their own information. Do not prefix generated
        # icons, even in semantic mode: the small semantic Emoji budget is
        # reserved for structural labels selected while parsing the source.
        display_date = date
        # Timeline rows are intentionally single-column. This gives dates and
        # long Chinese phrases the full phone width instead of forcing a date
        # into a narrow quarter-width column on small screens.
        if date_bold and date:
            row_elements: List[Dict[str, Any]] = [
                markdown(
                    bold_value(display_date),
                    text_size=date_size,
                    eid=element_id("timeline_date", row_number),
                )
            ]
        else:
            row_elements = [
                    div(
                    display_date,
                    text_size=date_size,
                    text_color=accent,
                    eid=element_id("timeline_date", row_number),
                )
            ]
        if title:
            row_elements.append(
                markdown(
                    bold_value(semantic_highlight(title, auto_emphasis)),
                    text_size=title_size,
                    eid=element_id("timeline_title", row_number),
                )
            )
        if content:
            row_elements.append(markdown(semantic_highlight(content, auto_emphasis), text_size="normal_v2", eid=element_id("timeline_detail", row_number)))
        columns = [
            {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "background_style": "grey-100" if focus else surface_style,
                "padding": "10px" if focus else "8px",
                "vertical_spacing": "4px",
                "elements": row_elements,
            }
        ]
        elements.append(
            {
                "tag": "column_set",
                "flex_mode": "none",
                "horizontal_spacing": "8px",
                "margin": "0px",
                "element_id": element_id("timeline_row", counter[0]),
                "columns": columns,
            }
        )
    return elements


def quote_element(
    spec: Dict[str, Any],
    counter: List[int],
    *,
    accent: str = GOLD,
    surface_style: str = "grey-50",
) -> Optional[Dict[str, Any]]:
    quote = spec.get("quote")
    if not isinstance(quote, dict):
        return None
    eyebrow = non_empty(quote.get("eyebrow"))
    title = non_empty(quote.get("title"))
    content = non_empty(quote.get("text", quote.get("content")))
    if not any((eyebrow, title, content)):
        return None
    quote_lines: List[str] = []
    emphasis = quote.get("emphasis") == "heading"
    if title:
        quote_lines.append(title if not emphasis or "**" in title else f"**{title}**")
    if content:
        if title:
            quote_lines.append("")
        quote_lines.append(content if not emphasis or "**" in content else f"**{content}**")
    counter[0] += 1
    inner: List[Dict[str, Any]] = []
    if eyebrow:
        inner.append(div(eyebrow, text_size="notation", text_color=accent, eid=element_id("quote_eyebrow", counter[0])))
    if quote_lines:
        inner.append(markdown("\n".join(quote_lines), text_size="heading" if emphasis else "normal_v2", eid=element_id("quote_text", counter[0])))
    return {
        "tag": "column_set",
        "flex_mode": "none",
        "horizontal_spacing": "8px",
        "margin": "0px",
        "element_id": element_id("quote", counter[0]),
        "columns": [
            {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "background_style": surface_style,
                "padding": "12px",
                "vertical_spacing": "4px",
                "elements": inner,
            }
        ],
    }


def safe_callback_value(value: Any, path: str = "value") -> Any:
    if isinstance(value, dict):
        result: Dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in FORBIDDEN_CALLBACK_KEYS:
                raise ValueError(f"callback {path} contains forbidden identity/secret field: {key_text}")
            result[key_text] = safe_callback_value(item, f"{path}.{key_text}")
        return result
    if isinstance(value, list):
        return [safe_callback_value(item, f"{path}[]") for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, str) and len(value) > 1024:
            raise ValueError(f"callback {path} contains a value longer than 1024 characters")
        return value
    raise ValueError(f"callback {path} contains unsupported data")


def action_behavior(item: Dict[str, Any], index: int, label: str, source_tag: str) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """Build one URL/callback behavior and its application-bot contract."""
    url = non_empty(item.get("url"))
    callback = item.get("callback")
    if url and callback:
        raise ValueError(f"{source_tag} {index} must choose url or callback, not both")
    if url:
        if not re.match(r"^(https://|http://|lark://|feishu://)", url) and not is_placeholder(url):
            raise ValueError(f"{source_tag} {index} open_url must use http(s), lark, or feishu scheme")
        return {"type": "open_url", "default_url": url}, None
    if callback is None:
        raise ValueError(f"{source_tag} {index} must provide url or callback")
    if isinstance(callback, str):
        callback = {"action": callback}
    if not isinstance(callback, dict):
        raise ValueError(f"{source_tag} {index} callback must be an object or action string")
    action = non_empty(callback.get("action"))
    if not action:
        raise ValueError(f"{source_tag} {index} callback is missing action")
    callback_value = callback.get("value", {})
    if not isinstance(callback_value, dict):
        raise ValueError(f"{source_tag} {index} callback value must be an object")
    callback_value = safe_callback_value(callback_value)
    callback_value = {**callback_value, "action": action}
    contract = {
        "action": action,
        "button_text": label,
        "source_tag": source_tag,
        "event": "card.action.trigger",
        "operator": "verified event operator_id",
        "permission_mode": callback.get("permission_mode", "server_authorized"),
        "required_capabilities": callback.get("required_capabilities", []),
        "handler": callback.get("handler", "application backend"),
        "states": ["initial", "pending", "confirmed", "error"],
        "idempotency": "action + card_instance_id + verified operator_id",
    }
    return {"type": "callback", "value": callback_value}, contract


def button_elements(
    spec: Dict[str, Any],
    counter: List[int],
    *,
    source_tag: str = "button",
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    buttons = [button for button in (spec.get("buttons", []) or []) if isinstance(button, dict)]
    if not buttons:
        return [], []
    actions: List[Dict[str, Any]] = []
    contracts: List[Dict[str, Any]] = []
    styles = {"primary": "primary_filled", "secondary": "default", "default": "default", "danger": "danger_filled"}
    for index, item in enumerate(buttons, start=1):
        label = non_empty(item.get("text", item.get("label")))
        if not label:
            raise ValueError(f"button {index} is missing text")
        behavior, contract = action_behavior(item, index, label, source_tag)
        if contract:
            contracts.append(contract)
        counter[0] += 1
        button: Dict[str, Any] = {
            "tag": "button",
            "text": plain(label),
            "type": styles.get(as_text(item.get("style", "secondary")), "default"),
            "width": "fill",
            "behaviors": [behavior],
            "element_id": element_id("button", counter[0]),
        }
        actions.append(button)
    # Card 2.0 buttons are direct elements. The old `action` container is a
    # Card 1.0 pattern and is rejected by current Feishu message APIs.
    return actions, contracts


def make_asset_plan(
    spec: Dict[str, Any],
    output: Path,
    *,
    persist: bool = True,
    preset: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    hero = spec.get("hero")
    if not isinstance(hero, dict) or hero.get("img_key"):
        return None
    prompt = non_empty(hero.get("prompt"))
    if not prompt:
        prompt = non_empty((preset or {}).get("hero_prompt")) or "现代东方留白、暖纸色、墨黑飞书标志意象、香槟金汇聚路径与微妙节点；纯粹、克制、先锋；无文字、无水印、适合飞书卡片首图。"
    runtime = image_runtime()
    image_generation_mode = non_empty(hero.get("image_generation_mode")) or default_image_mode()
    if image_generation_mode not in supported_image_modes():
        raise ValueError(
            f"unsupported image_generation_mode: {image_generation_mode}; "
            f"use one of {', '.join(supported_image_modes())}"
        )
    mode_config = image_mode_config(image_generation_mode)
    image_source = non_empty(hero.get("image_source")) or "ai_generated"
    is_ai_image = image_source != "real_image"
    generation_model = (
        non_empty(hero.get("generation_model"))
        or (str(runtime.get("generation_model") or "").strip() if is_ai_image else None)
    )
    generation_model_label = (
        non_empty(hero.get("generation_model_label"))
        or (str(runtime.get("generation_model_label") or "").strip() if is_ai_image else None)
    )
    text_policy = non_empty(hero.get("text_in_image")) or str(
        mode_config.get("text_policy") or "seedream_5_pro_direct_selected_text_and_layout"
    )
    plan = {
        "status": "needs_img_key",
        "card_field": "body.elements[hero].img_key",
        "asset_kind": non_empty(hero.get("asset_kind")) or "image",
        "image_source": image_source,
        "image_roles": hero.get("image_roles", []),
        "generation_family": non_empty(hero.get("generation_family")) if is_ai_image else None,
        "generation_tool": non_empty(hero.get("generation_tool")) if is_ai_image else None,
        "generation_model": generation_model,
        "generation_model_label": generation_model_label,
        "generation_provenance": non_empty(hero.get("generation_provenance")) if is_ai_image else None,
        "role": non_empty(hero.get("role")) or "information_anchor",
        "information_carrier": bool(hero.get("information_carrier", True)),
        "text_in_image": text_policy,
        "functional_text": hero.get("functional_text", []),
        "functional_text_source_locked": bool(hero.get("functional_text_source_locked", True)),
        "information_allocation": spec.get("information_allocation", {}),
        "source_url": non_empty(hero.get("source_url")),
        "source_markers": hero.get("source_markers", []),
        "style": (preset or {}).get("name", "飞书 AI 先锋大赛"),
        "prompt": prompt,
        "motion": non_empty(hero.get("motion")) if non_empty(hero.get("asset_kind")) == "gif" else None,
        "constraints": [
            f"AI 图片：默认先调用或读取 Guizang Social Card Skill 与 baoyu-skills 的内容/视觉方法，再用 豆包工作 内置 image_gen 的 Seedream 5.0 Pro-class（{generation_model_label or 'Seedream 5.0 Pro'}）步骤一次性生成 {mode_config.get('label', '最终图片')}；图片只渲染 information_allocation.image.include 中的短标题、关系节点、指标和必要 quote，严禁按钮、CTA 标签或伪交互；原生 Card 只保留精简摘要、关键点、图表和真实行动，完整原文保留在 source.txt；登记 hero-generation.json 后直接上传 hero.png，并把返回的 img_key 写入 spec.hero.img_key；禁止 Pillow、HTML/CSS/SVG、文字叠加、图片拼接或其他图片模型后处理。",
            "真实图片：保留原始像素、尺寸、来源和 alt；先用 scripts/media_assets.py 生成媒体 manifest，再将真实图片与相邻原生事实/按钮配对，不把真实截图重绘成装饰图。",
            "图片必须表达主题关系、阶段或分组，不得只做装饰。",
            "图片内必须由 Seedream 5.0 Pro 直接呈现 information_allocation.image.include 对应的全部来源锁定文字、日期、阶段动作、指标和必要 quote；不得呈现按钮、CTA 标签、URL 或伪交互；未分配给图片的长文和完整事实保留在 source.txt，原生 Card 只做精简可编辑摘要；文字准确性和无伪按钮状态必须人工逐字复核。",
            "不得使用文字后处理、图片拼接或第二个模型修正图片；发现问题只能重新调用 Seedream 5.0 Pro。",
            "优先静态图；GIF 只用于轻微流动或节点聚合，不使用高频闪烁。",
        ],
    }
    if not persist:
        return None
    plan_path = output.with_suffix(".asset-plan.json")
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return plan_path


def collapsible_panel(
    title: str,
    elements: List[Dict[str, Any]],
    counter: List[int],
    *,
    surface_style: str = "grey-50",
) -> Dict[str, Any]:
    counter[0] += 1
    return {
        "tag": "collapsible_panel",
        "expanded": False,
        "header": {
            "title": plain(title),
            "icon": {"tag": "standard_icon", "token": "down_outlined", "color": "grey"},
            "icon_position": "right",
            "icon_expanded_angle": -180,
            "background_color": surface_style,
            "width": "fill",
            "vertical_align": "center",
        },
        "background_color": surface_style,
        "border": {"color": "grey-200", "corner_radius": "8px"},
        "padding": "8px",
        "vertical_spacing": "8px",
        "margin": "0px",
        "element_id": element_id("supporting_panel", counter[0]),
        "elements": elements,
    }


def build_card(
    spec: Dict[str, Any],
    output: Path,
    *,
    persist_assets: bool = True,
) -> Tuple[Dict[str, Any], Optional[Path], List[Dict[str, Any]]]:
    scene = resolve_scene(spec)
    card_type = (non_empty(spec.get("type")) or (scene or {}).get("type") or "custom").lower()
    title = non_empty(spec.get("title")) or "飞书 AI 先锋卡片"
    subtitle = non_empty(spec.get("subtitle"))
    requested_summary = non_empty(spec.get("summary"))
    preset = resolve_preset(spec, scene)
    if preset:
        accent = non_empty(preset.get("accent_token")) or GOLD
        surface_style = non_empty(preset.get("surface_style")) or "grey-50"
        timeline_surface_style = non_empty(preset.get("timeline_surface_style")) or surface_style
    else:
        accent = GOLD
        surface_style = "grey-50"
        timeline_surface_style = "grey-50"
    auto_emphasis = bool(spec.get("auto_emphasis"))
    counter = [0]
    body: List[Dict[str, Any]] = []

    hero = spec.get("hero")
    hero_plan = None
    hero_elements: List[Dict[str, Any]] = []
    if isinstance(hero, dict) and non_empty(hero.get("img_key")):
        counter[0] += 1
        hero_elements.append(
            {
                "tag": "img",
                "img_key": non_empty(hero.get("img_key")),
                "alt": plain(non_empty(hero.get("alt")) or "飞书 AI 先锋大赛视觉首图"),
                "scale_type": "crop_center",
                "size": "stretch",
                "corner_radius": "8px",
                "preview": True,
                "margin": "0px",
                "element_id": element_id("hero", counter[0]),
            }
        )
    elif isinstance(hero, dict):
        hero_plan = make_asset_plan(spec, output, persist=persist_assets, preset=preset)

    eyebrow_elements: List[Dict[str, Any]] = []
    eyebrow = non_empty(spec.get("eyebrow"))
    if not eyebrow and card_type in TYPE_LABELS and not spec.get("suppress_generated_labels"):
        eyebrow = TYPE_LABELS[card_type]
    if eyebrow:
        counter[0] += 1
        eyebrow_elements.append(div(eyebrow, text_size="notation", text_color=accent, eid=element_id("eyebrow", counter[0])))

    lead_elements: List[Dict[str, Any]] = []
    lead = non_empty(spec.get("lead"))
    if lead:
        lead_elements.append(
            highlight_element(
                {
                    "label": spec.get("lead_label"),
                    "content": lead,
                    "tone": spec.get("lead_tone", "brand"),
                    "element_id": "lead",
                },
                counter,
                accent=accent,
                surface_style=surface_style,
                auto_emphasis=auto_emphasis,
            )
        )
        lead_elements = [element for element in lead_elements if element]

    facts_elements = fact_elements(spec, counter, accent=accent, surface_style=surface_style)
    sections_elements = section_elements(spec, counter, accent=accent, surface_style=surface_style, auto_emphasis=auto_emphasis)
    timeline_content = timeline_elements(spec, counter, accent=accent, surface_style=timeline_surface_style, auto_emphasis=auto_emphasis)
    # Some notices intentionally place a short encouragement or callout after
    # the timeline. Keeping this as an explicit field preserves the user's
    # reading order instead of silently reordering content by component type.
    after_timeline_elements = section_elements(spec, counter, field="after_timeline", accent=accent, surface_style=surface_style, auto_emphasis=auto_emphasis)

    quote = quote_element(spec, counter, accent=accent, surface_style=surface_style)
    actions, contracts = button_elements(spec, counter)
    footer_elements: List[Dict[str, Any]] = []
    footer = non_empty(spec.get("footer"))
    if footer:
        counter[0] += 1
        footer_elements.append({"tag": "hr", "margin": "0px", "element_id": element_id("footer_rule", counter[0])})
        counter[0] += 1
        footer_elements.append(markdown(footer, text_size="notation", eid=element_id("footer", counter[0])))

    explicit_blocks = spec.get("blocks")
    if isinstance(explicit_blocks, list):
        has_timeline_block = any(isinstance(block, dict) and block.get("type") == "timeline" for block in explicit_blocks)
        lead_in_blocks = bool(
            lead and lead in json.dumps(explicit_blocks, ensure_ascii=False)
        )
        ordered_blocks = explicit_blocks
        if spec.get("timeline_first") and has_timeline_block:
            # Auto-layout marks a timeline-first card when the dates/actions
            # are the information focus.  Keep milestone order intact while
            # putting that instrument before the decorative hero and prose.
            ordered_blocks = [
                *[block for block in explicit_blocks if isinstance(block, dict) and block.get("type") == "timeline"],
                *[block for block in explicit_blocks if not (isinstance(block, dict) and block.get("type") == "timeline")],
            ]
        block_content, block_contracts = block_elements(
            ordered_blocks,
            counter,
            accent=accent,
            surface_style=surface_style,
            auto_emphasis=auto_emphasis,
        )
        if spec.get("timeline_first") and has_timeline_block:
            body.extend(block_content)
            body.extend(hero_elements)
            body.extend(eyebrow_elements)
            if not lead_in_blocks:
                body.extend(lead_elements)
        else:
            body.extend(hero_elements)
            body.extend(eyebrow_elements)
            if not lead_in_blocks:
                body.extend(lead_elements)
            body.extend(block_content)
        if actions:
            body.extend(actions)
        contracts.extend(block_contracts)
        advanced_elements = spec.get("advanced_elements")
        if isinstance(advanced_elements, list):
            for item in advanced_elements:
                if not isinstance(item, dict) or item.get("tag") not in SUPPORTED_RAW_BLOCK_TAGS:
                    raise ValueError("advanced_elements must contain supported Feishu component objects")
                body.append(dict(item))
        body.extend(footer_elements)
    elif spec.get("timeline_first"):
        # A timeline card is an information instrument first. Put the core
        # schedule before the decorative hero and collapse supporting prose so
        # a 10-second phone scan answers the date question immediately.
        body.extend(timeline_content)
        body.extend(facts_elements)
        body.extend(hero_elements)
        supporting = lead_elements + eyebrow_elements + sections_elements + after_timeline_elements
        if quote:
            supporting.append(quote)
        if supporting and spec.get("collapse_supporting", True):
            body.append(
                collapsible_panel(
                    non_empty(spec.get("supporting_title")) or "展开补充信息 · 开营说明与理念",
                    supporting,
                    counter,
                    surface_style=surface_style,
                )
            )
        else:
            body.extend(supporting)
        body.extend(actions)
        body.extend(footer_elements)
    else:
        body.extend(hero_elements)
        body.extend(eyebrow_elements)
        body.extend(lead_elements)
        body.extend(facts_elements)
        body.extend(sections_elements)
        body.extend(timeline_content)
        body.extend(after_timeline_elements)
        if quote:
            body.append(quote)
        body.extend(actions)
        advanced_elements = spec.get("advanced_elements")
        if isinstance(advanced_elements, list):
            for item in advanced_elements:
                if not isinstance(item, dict) or item.get("tag") not in SUPPORTED_RAW_BLOCK_TAGS:
                    raise ValueError("advanced_elements must contain supported Feishu component objects")
                body.append(dict(item))
        body.extend(footer_elements)

    summary_spec = dict(spec)
    if requested_summary:
        summary_spec["summary"] = requested_summary
    summary = build_card_summary(summary_spec, title, body)

    theme = (non_empty(spec.get("theme")) or "oriental").lower()
    header_template = non_empty(spec.get("header_template")) or (preset or {}).get("header_template") or THEME_HEADER_TEMPLATES.get(theme, "grey")
    header: Dict[str, Any] = {
        "title": plain(title),
        "template": header_template,
        "padding": "12px 12px 12px 12px",
    }
    if subtitle:
        header["subtitle"] = plain(subtitle)
    if spec.get("logo", True):
        header["icon"] = {"tag": "standard_icon", "token": spec.get("header_icon_token", "lark-logo_colorful")}
    date_label = non_empty(spec.get("date_label"))
    if date_label:
        header["text_tag_list"] = [{"tag": "text_tag", "text": plain(date_label), "color": (preset or {}).get("header_tag_color", "yellow")}]

    width_mode = non_empty(spec.get("width_mode")) or "default"
    if width_mode not in {"default", "compact", "fill"}:
        width_mode = "default"
    if not non_empty(spec.get("width_mode")) and preset:
        width_mode = (preset.get("width_mode") or width_mode) if (preset.get("width_mode") or width_mode) in {"default", "compact", "fill"} else width_mode
    accent_light = (preset or {}).get("accent_light_mode", "rgba(234,205,118,1)")
    accent_dark = (preset or {}).get("accent_dark_mode", "rgba(248,226,160,1)")
    card: Dict[str, Any] = {
        "schema": "2.0",
        "config": {
            "update_multi": True,
            "enable_forward": True,
            "width_mode": width_mode,
            "summary": {"content": summary},
        },
        "header": header,
        "body": {
            "direction": "vertical",
            "padding": spec.get("body_padding") or (preset or {}).get("body_padding", "12px 12px 20px 12px"),
            "vertical_spacing": spec.get("vertical_spacing") or (preset or {}).get("vertical_spacing", "8px"),
            "elements": body,
        },
    }
    card_link = spec.get("card_link")
    if isinstance(card_link, str) and card_link.strip():
        card["card_link"] = {"url": card_link.strip()}
    elif isinstance(card_link, dict):
        card["card_link"] = dict(card_link)
    return card, hero_plan, contracts


def read_spec(args: argparse.Namespace) -> Dict[str, Any]:
    if args.spec:
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
        if not isinstance(spec, dict):
            raise ValueError("spec root must be a JSON object")
    else:
        if args.text_file:
            text = Path(args.text_file).read_text(encoding="utf-8")
        elif args.text is not None:
            text = args.text
        else:
            raise ValueError("provide --spec, --text, or --text-file")
        if args.layout == "auto":
            spec = build_auto_spec(
                text,
                requested_type=args.type,
                requested_scene=args.scene,
                requested_preset=args.preset,
                emoji_mode=args.emoji_mode,
                dedupe="off" if args.dedupe == "preserve" else args.dedupe,
                link_mode=args.link_mode,
            )
        else:
            lines = [line for line in text.splitlines()]
            first = next((line.strip() for line in lines if line.strip()), "飞书 AI 先锋卡片")
            remainder_started = False
            remainder: List[str] = []
            for line in lines:
                if not remainder_started and line.strip() == first:
                    remainder_started = True
                    continue
                if remainder_started:
                    remainder.append(line)
            spec = {"title": args.title or first, "lead": "\n".join(remainder).strip()}
            if args.type:
                spec["type"] = args.type
            elif not args.scene:
                spec["type"] = "custom"
    if args.type:
        spec["type"] = args.type
    if args.title:
        spec["title"] = args.title
    if args.scene:
        spec["scene"] = args.scene
    if args.preset:
        spec["preset"] = args.preset
    if args.hero_img_key:
        spec["hero"] = {**(spec.get("hero") if isinstance(spec.get("hero"), dict) else {}), "img_key": args.hero_img_key}
    if spec.get("emoji_normalize"):
        spec = normalize_emoji_aliases(spec)
    return spec


SCENE_FIELD_BLOCK_TYPES = {
    "facts": {"facts", "metrics"},
    "sections": {"section", "markdown", "text", "div"},
    "timeline": {"timeline"},
    "buttons": {"buttons", "button"},
    "quote": {"quote"},
}


def _blocks_contain_type(blocks: Any, aliases: set[str]) -> bool:
    if not isinstance(blocks, list):
        return False
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if str(block.get("type", block.get("kind", ""))).lower() in aliases:
            return True
        children = block.get("blocks", block.get("elements", []))
        if _blocks_contain_type(children, aliases):
            return True
    return False


def spec_field_present(spec: Dict[str, Any], field: str) -> bool:
    value = spec.get(field)
    if isinstance(value, str):
        if value.strip():
            return True
    elif isinstance(value, (list, dict)):
        if value:
            return True
    elif value is not None:
        return True
    aliases = SCENE_FIELD_BLOCK_TYPES.get(field, set())
    if aliases and _blocks_contain_type(spec.get("blocks"), aliases):
        return True
    return False


def scene_contract_report(spec: Dict[str, Any], scene: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not scene:
        return None
    required = [field for field in scene.get("required_fields", []) if isinstance(field, str)]
    missing = [field for field in required if not spec_field_present(spec, field)]
    recommended = [field for field in scene.get("recommended_fields", []) if isinstance(field, str)]
    recommended_missing = [field for field in recommended if not spec_field_present(spec, field)]
    return {
        "ok": not missing,
        "required_fields": required,
        "missing_fields": missing,
        "recommended_fields": recommended,
        "recommended_missing_fields": recommended_missing,
        "remediation": "补齐缺失字段，或在 blocks 中使用对应组件后再发送。" if missing else None,
    }


def compile_outputs(
    spec: Dict[str, Any],
    output: Path,
    *,
    editable_spec: Optional[Path] = None,
    persist_assets: bool = True,
    brand_context: str = "",
    style_output: Optional[Path] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Write the source spec and compiled artifacts as one repeatable unit."""
    output.parent.mkdir(parents=True, exist_ok=True)
    card, hero_plan, contracts = build_card(spec, output, persist_assets=persist_assets)
    output.write_text(json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    interaction_path: Optional[Path] = None
    if contracts:
        interaction_path = output.with_suffix(".interaction.json")
        interaction = {
            "version": "1.0",
            "surface": "application-bot",
            "event": "card.action.trigger",
            "actions": contracts,
            "security": {
                "operator_source": "verify event context; never trust a user id from card value",
                "idempotency": "action + card_instance_id + verified operator_id",
                "public_distribution": "authorize tenant, role, and resource on the server",
            },
        }
        interaction_path.write_text(json.dumps(interaction, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    style_path: Optional[Path] = None
    analysis = spec.get("analysis") if isinstance(spec.get("analysis"), dict) else {}
    source_text = analysis.get("source_text") if isinstance(analysis, dict) else None
    if isinstance(source_text, str) and source_text.strip():
        existing_style = analysis.get("style_document") if isinstance(analysis, dict) else None
        if isinstance(existing_style, dict) and existing_style.get("path"):
            style_path = Path(str(existing_style["path"])).expanduser().resolve()
        else:
            style_path = (style_output or output.with_suffix(".style.md")).expanduser().resolve()
            style_path.parent.mkdir(parents=True, exist_ok=True)
            requested_preset = spec.get("preset") if isinstance(spec.get("preset"), str) else None
            style_path.write_text(
                build_style_document(source_text, brand_context=brand_context, preset=requested_preset),
                encoding="utf-8",
            )
            analysis["style_document"] = {
                "path": str(style_path),
                "style_id": infer_style(source_text, brand_context, requested_preset)["style_id"],
                "source": "input_and_brand_context",
            }

    # Persist the editable source only after style.md metadata has been added,
    # so a later human/CardKit edit can discover the exact style contract from
    # the sibling spec without relying on the report.
    if editable_spec is not None:
        editable_spec.parent.mkdir(parents=True, exist_ok=True)
        editable_spec.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    resolved_scene = resolve_scene(spec)
    resolved_preset = resolve_preset(spec, resolved_scene)
    scene_contract = scene_contract_report(spec, resolved_scene)
    report = {
        "card": str(output),
        "editable_spec": str(editable_spec) if editable_spec else None,
        "style": str(style_path) if style_path else None,
        "type": spec.get("type") or (resolved_scene or {}).get("type", "custom"),
        "scene": resolved_scene.get("id") if resolved_scene else None,
        "preset": resolved_preset.get("id") if resolved_preset else None,
        "callbacks": len(contracts),
        "asset_plan": str(hero_plan) if hero_plan else None,
        "interaction_contract": str(interaction_path) if interaction_path else None,
        "content_analysis": spec.get("analysis") if isinstance(spec.get("analysis"), dict) else None,
        "design_plan": spec.get("analysis", {}).get("design_plan") if isinstance(spec.get("analysis"), dict) else None,
        "decision_log": spec.get("analysis", {}).get("decision_log", []) if isinstance(spec.get("analysis"), dict) else [],
        "scene_contract": scene_contract,
        "sendable": not bool(hero_plan) and not contains_placeholder(card) and (scene_contract is None or scene_contract["ok"]),
        "preview_command": f"可选本地调试：python3 scripts/preview_card.py --spec {editable_spec or output.with_suffix('.spec.json')} --output {output}",
        "cardkit_import_command": f"python3 scripts/feishu_cli.py push-cardkit --card {shlex.quote(str(output))} --dry-run",
    }
    return card, report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(allow_abbrev=False, description="Generate a mobile-safe Feishu AI Pioneer Card 2.0 JSON file")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--spec", help="structured JSON spec")
    source.add_argument("--text", help="card copy; first non-empty line becomes the title")
    source.add_argument("--text-file", help="UTF-8 card copy file")
    parser.add_argument("--type", choices=sorted(TYPE_LABELS), help="card type")
    parser.add_argument("--title", help="override the card title")
    parser.add_argument("--scene", help="event lifecycle scene id, for example training-notice")
    parser.add_argument("--preset", help="built-in visual preset id, for example pioneer-red")
    parser.add_argument("--layout", choices=("auto", "plain"), default="auto", help="plain-text layout mode; auto extracts dates, links, focus, and scene")
    parser.add_argument("--emoji-mode", choices=("auto", "aliases", "semantic", "off"), default="semantic", help="default adds 3–6 restrained semantic Emoji; use off to disable")
    parser.add_argument("--dedupe", choices=("safe", "preserve"), default="safe", help="remove exact repeated lines from the rendered layout while preserving the source in analysis")
    parser.add_argument("--link-mode", choices=("button", "inline"), default="button", help="route detected URLs to buttons without repeating them in body text, or keep inline URLs")
    parser.add_argument("--hero-img-key", help="real Feishu img_key returned by the image upload API")
    parser.add_argument("--brand-context", default="", help="verified project/brand facts used to generate style.md")
    parser.add_argument("--brand-context-file", help="UTF-8 file containing verified project/brand facts")
    parser.add_argument("--style-output", help="optional style.md output path")
    parser.add_argument("--output", required=True, help="output .card path")
    parser.add_argument("--spec-output", help="editable source spec path; defaults to a sibling .spec.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        spec = read_spec(args)
        brand_context = args.brand_context
        if args.brand_context_file:
            brand_context = Path(args.brand_context_file).read_text(encoding="utf-8")
        output = Path(args.output).expanduser().resolve()
        editable_spec = Path(args.spec_output).expanduser().resolve() if args.spec_output else output.with_suffix(".spec.json")
        _, report = compile_outputs(
            spec,
            output,
            editable_spec=editable_spec,
            brand_context=brand_context,
            style_output=Path(args.style_output) if args.style_output else None,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"generate_card.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
