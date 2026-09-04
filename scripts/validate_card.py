#!/usr/bin/env python3
"""Validate a generated Feishu Card 2.0 payload and mobile layout hazards."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


TEXT_SIZES = {"heading", "normal_v2", "notation", "heading-1", "heading-2", "heading-3", "heading-4"}
SURFACES = {"raw", "custom-bot", "application-bot"}
ELEMENT_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,19}$")
KNOWN_TAGS = {
    "column_set",
    "column",
    "collapsible_panel",
    "collapse_divider",
    "interactive_container",
    "form",
    "div",
    "markdown",
    "plain_text",
    "lark_md",
    "text_tag",
    "custom_icon",
    "ud_icon",
    "img",
    "img_combination",
    "avatar",
    "video",
    "fallback_text",
    "person",
    "person_list",
    "chart",
    "table",
    "audio",
    "hr",
    "button",
    "overflow",
    "input",
    "select_static",
    "multi_select_static",
    "select_person",
    "multi_select_person",
    "standard_icon",
    "date_picker",
    "picker_date",
    "picker_time",
    "picker_datetime",
    "select_img",
    "checker",
    "action",
}
FORM_INTERACTIVE_TAGS = {
    "input",
    "button",
    "overflow",
    "select_static",
    "multi_select_static",
    "select_person",
    "multi_select_person",
    "date_picker",
    "picker_date",
    "picker_time",
    "picker_datetime",
    "select_img",
    "checker",
}
HEADER_TEMPLATES = {"blue", "wathet", "turquoise", "green", "yellow", "orange", "red", "carmine", "violet", "purple", "indigo", "grey", "default"}
# CardKit's editor accepts the platform color names in text_color.  Custom
# aliases may survive the first import but are dropped from config.style.color
# during CardKit normalization, which makes a later manual edit fail.
CARDKIT_TEXT_COLORS = frozenset(HEADER_TEMPLATES)
LEGACY_CARDKIT_TEXT_COLOR_ALIASES = {
    "brand_accent": "blue",
    "brand_gold": "yellow",
    "brand_ink": "grey",
}
FORBIDDEN_CALLBACK_KEYS = {"user_id", "open_id", "union_id", "tenant_key", "access_token", "refresh_token", "secret", "webhook"}
COLLAPSIBLE_PANEL_ICON = {"tag": "standard_icon", "token": "down_outlined", "color": "grey"}


def normalize_cardkit_text_color(value: Any) -> Any:
    """Convert legacy custom text-color aliases to CardKit-native names."""
    if not isinstance(value, str):
        return value
    return LEGACY_CARDKIT_TEXT_COLOR_ALIASES.get(value, value)


def _markdown_table_alignment_errors(content: str, path: str) -> List[str]:
    """Apply the Card Studio house rule for Markdown table delimiters."""
    errors: List[str] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if "|" not in stripped:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2 or not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        if not all(re.fullmatch(r":-{3,}", cell) for cell in cells):
            errors.append(
                f"{path} Markdown table delimiter line {line_number} must use :--- for every column; right/center alignment is not supported"
            )
    return errors


def _collapsible_panel_errors(node: Dict[str, Any], path: str) -> List[str]:
    header = node.get("header")
    if not isinstance(header, dict):
        return [f"{path}.header must contain the standard collapsible-panel arrow icon"]
    errors: List[str] = []
    if header.get("icon") != COLLAPSIBLE_PANEL_ICON:
        errors.append(f"{path}.header.icon must be {json.dumps(COLLAPSIBLE_PANEL_ICON, ensure_ascii=False)}")
    if header.get("icon_position") != "right":
        errors.append(f"{path}.header.icon_position must be right")
    if header.get("icon_expanded_angle") != -180:
        errors.append(f"{path}.header.icon_expanded_angle must be -180")
    return errors


def _unwrap_card_for_validation(card: Any) -> Tuple[Any, str, List[str]]:
    """Accept raw Card JSON and the CardKit ``name/dsl/variables`` envelope."""
    if isinstance(card, list):
        if not card:
            return card, "array", ["card document array is empty"]
        card = card[0]
    if not isinstance(card, dict) or "dsl" not in card:
        return card, "raw", []
    dsl = card.get("dsl")
    if isinstance(dsl, str):
        try:
            dsl = json.loads(dsl)
        except json.JSONDecodeError as exc:
            return None, "cardkit", [f"CardKit wrapper dsl is not valid JSON: {exc}"]
    if not isinstance(dsl, dict):
        return None, "cardkit", ["CardKit wrapper dsl must be an object"]
    return dsl, "cardkit", []


def find_forbidden_callback_key(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in FORBIDDEN_CALLBACK_KEYS:
                return str(key)
            found = find_forbidden_callback_key(item)
            if found is not None:
                return found
        return None
    if isinstance(value, list):
        for item in value:
            found = find_forbidden_callback_key(item)
            if found is not None:
                return found
    return None


def is_placeholder(value: str) -> bool:
    lowered = value.lower()
    return "${" in value or "example.com" in lowered or "replace_me" in lowered or "your_" in lowered or "_mock_" in lowered or lowered.startswith("mock_")


def url_like(value: str) -> bool:
    return bool(re.match(r"^(https://|http://|lark://|feishu://)", value))


def text_length(node: Any) -> int:
    if isinstance(node, str):
        return len(node)
    if isinstance(node, dict):
        return sum(text_length(value) for value in node.values())
    if isinstance(node, list):
        return sum(text_length(value) for value in node)
    return 0


def visible_text_length(node: Any) -> int:
    """Count rendered text, excluding JSON key names and layout metadata."""
    if isinstance(node, str):
        return 0
    if isinstance(node, dict):
        total = 0
        if isinstance(node.get("content"), str):
            total += len(node["content"])
        for key, value in node.items():
            if key != "content":
                total += visible_text_length(value)
        return total
    if isinstance(node, list):
        return sum(visible_text_length(value) for value in node)
    return 0


def validate(card: Any, *, surface: str = "raw", allow_placeholders: bool = False) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    ids: Set[str] = set()
    form_names: Set[str] = set()
    stats = {"bytes": 0, "elements": 0, "images": 0, "buttons": 0, "callbacks": 0, "tables": 0, "charts": 0, "forms": 0, "max_container_depth": 0, "placeholders": 0, "visible_text_chars": 0, "max_text_block_chars": 0, "emoji_count": 0}
    card, document_format, unwrap_errors = _unwrap_card_for_validation(card)
    errors.extend(unwrap_errors)

    if surface not in SURFACES:
        errors.append(f"unknown surface: {surface}")
    if not isinstance(card, dict):
        return {"ok": False, "errors": errors + ["card root must be an object"], "warnings": [], "stats": stats, "document_format": document_format}
    if card.get("schema") != "2.0":
        errors.append('schema must be "2.0"')
    config = card.get("config")
    if not isinstance(config, dict):
        errors.append("config must be an object")
    else:
        if config.get("update_multi") is not True:
            errors.append("config.update_multi must be true for stable card updates")
        elif config.get("width_mode") is not None and config.get("width_mode") not in {"default", "compact", "fill"}:
            errors.append("config.width_mode must be default, compact, or fill")
        summary = config.get("summary")
        if summary is not None:
            summary_content = summary.get("content") if isinstance(summary, dict) else None
            if not isinstance(summary_content, str) or not 8 <= len(summary_content.strip()) <= 60:
                warnings.append("config.summary.content should contain 8-60 characters for message-list context")
            elif is_placeholder(summary_content):
                warnings.append("config.summary.content should not be a placeholder")
    header = card.get("header")
    if not isinstance(header, dict) or not isinstance(header.get("title"), dict):
        errors.append("header.title is required")
    elif header.get("template") is not None and header.get("template") not in HEADER_TEMPLATES:
        warnings.append(f"header.template={header.get('template')!r} is not in the stable template set")
    body = card.get("body")
    if not isinstance(body, dict) or not isinstance(body.get("elements"), list):
        errors.append("body.elements must be an array")
        return {"ok": not errors, "errors": errors, "warnings": warnings, "stats": stats, "document_format": document_format}

    def visit(
        node: Any,
        path: str,
        depth: int = 0,
        inside_form: bool = False,
        inside_interactive: bool = False,
        parent_tag: str | None = None,
    ) -> None:
        if isinstance(node, list):
            for index, item in enumerate(node):
                visit(item, f"{path}[{index}]", depth, inside_form, inside_interactive, parent_tag)
            return
        if not isinstance(node, dict):
            return
        tag = node.get("tag")
        content = node.get("content")
        if isinstance(content, str):
            stats["visible_text_chars"] += len(content)
            stats["max_text_block_chars"] = max(stats["max_text_block_chars"], len(content))
            stats["emoji_count"] += len(re.findall(r"[\U0001F1E6-\U0001FAFF\u2300-\u27BF]", content))
        if tag:
            stats["elements"] += 1
            if tag not in KNOWN_TAGS:
                warnings.append(f"{path} uses an unknown component tag: {tag}")
        if tag == "markdown" and isinstance(node.get("content"), str):
            errors.extend(_markdown_table_alignment_errors(node["content"], f"{path}.content"))
        if tag == "collapsible_panel":
            errors.extend(_collapsible_panel_errors(node, path))
        if tag == "column" and "weight" in node and node.get("weight") != 1:
            errors.append(f"{path}.weight must be 1 for equal-width Card Studio columns")
        if "element_id" in node:
            eid = node.get("element_id")
            if not isinstance(eid, str) or not eid:
                errors.append(f"{path}.element_id must be a non-empty string")
            elif not ELEMENT_ID_RE.match(eid):
                errors.append(f"{path}.element_id must match ^[A-Za-z][A-Za-z0-9_]{{0,19}}$")
            elif eid in ids:
                errors.append(f"duplicate element_id: {eid}")
            else:
                ids.add(eid)
        if tag in {"column_set", "collapsible_panel", "interactive_container", "form", "action"}:
            stats["max_container_depth"] = max(stats["max_container_depth"], depth + 1)
        if tag == "action":
            errors.append(f"{path} uses the deprecated Card 1.0 action container; put buttons directly in elements")
        if tag == "table" and parent_tag is not None:
            errors.append(f"{path} table components are only supported directly in body.elements; use left-aligned Markdown inside containers")
        if tag == "form" and parent_tag is not None:
            errors.append(f"{path} form containers are only supported directly in body.elements")
        if tag == "img":
            stats["images"] += 1
            key = node.get("img_key")
            if not isinstance(key, str) or not key:
                errors.append(f"{path}.img_key is required")
            elif key.startswith(("http://", "https://", "/", "data:")) or is_placeholder(key):
                stats["placeholders"] += 1
                message = f"{path}.img_key must be a real Feishu img_key, not a URL/path/placeholder"
                if allow_placeholders and is_placeholder(key) and not key.startswith(("http://", "https://", "/", "data:")):
                    warnings.append(message)
                else:
                    errors.append(message)
            alt = node.get("alt")
            if not isinstance(alt, dict) or not alt.get("content"):
                warnings.append(f"{path}.alt is missing; add accessible image text")
        if tag == "img_combination":
            items = node.get("img_list")
            mode = node.get("combination_mode")
            limits = {"double": 2, "triple": 3, "bisect": 6, "trisect": 9}
            if mode not in limits:
                errors.append(f"{path}.combination_mode must be double, triple, bisect, or trisect")
            if not isinstance(items, list) or not items:
                errors.append(f"{path}.img_list must be a non-empty array")
            elif mode in limits and len(items) > limits[mode]:
                errors.append(f"{path}.img_list exceeds the {mode} image limit")
            for index, item in enumerate(items or []):
                stats["images"] += 1
                if not isinstance(item, dict) or not isinstance(item.get("img_key"), str) or not item.get("img_key"):
                    errors.append(f"{path}.img_list[{index}].img_key is required")
                elif item["img_key"].startswith(("http://", "https://", "/", "data:")) or is_placeholder(item["img_key"]):
                    stats["placeholders"] += 1
                    message = f"{path}.img_list[{index}].img_key must be a real Feishu img_key"
                    if allow_placeholders and is_placeholder(item["img_key"]) and not item["img_key"].startswith(("http://", "https://", "/", "data:")):
                        warnings.append(message)
                    else:
                        errors.append(message)
        if tag == "button":
            stats["buttons"] += 1
            if "form_action_type" in node:
                errors.append(f"{path}.form_action_type is invalid in Card 2.0; use action_type")
            action_type = node.get("action_type")
            if action_type is not None and action_type not in {"form_submit", "form_reset"}:
                errors.append(f"{path}.action_type must be form_submit or form_reset")
            behaviors = node.get("behaviors")
            if action_type == "form_reset" and behaviors is None:
                behaviors = []
            if not isinstance(behaviors, list) or len(behaviors) > 1:
                errors.append(f"{path}.behaviors must contain exactly one behavior")
            else:
                if not behaviors:
                    behavior = None
                else:
                    behavior = behaviors[0]
                if not isinstance(behavior, dict):
                    if action_type != "form_reset":
                        errors.append(f"{path}.behaviors[0] must be an object")
                else:
                    behavior_type = behavior.get("type")
                    if behavior_type == "open_url":
                        url = behavior.get("default_url")
                        if not isinstance(url, str):
                            errors.append(f"{path} open_url must contain an http(s)/lark/feishu URL")
                        elif is_placeholder(url):
                            stats["placeholders"] += 1
                            if not allow_placeholders:
                                errors.append(f"{path} URL is still a placeholder")
                            else:
                                warnings.append(f"{path} URL is a placeholder")
                        elif not url_like(url):
                            errors.append(f"{path} open_url must contain an http(s)/lark/feishu URL")
                    elif behavior_type == "callback":
                        stats["callbacks"] += 1
                        if surface == "custom-bot":
                            errors.append(f"{path} callback cannot be sent through custom-bot surface")
                        value = behavior.get("value")
                        if not isinstance(value, dict) or not isinstance(value.get("action"), str) or not value.get("action"):
                            errors.append(f"{path} callback needs value.action")
                        else:
                            forbidden_key = find_forbidden_callback_key(value)
                            if forbidden_key is not None:
                                errors.append(f"{path} callback value contains forbidden identity/secret field: {forbidden_key}")
                    else:
                        errors.append(f"{path} has unsupported behavior type: {behavior_type}")
        if tag == "form":
            stats["forms"] += 1
            if surface == "custom-bot":
                errors.append(f"{path} form cannot be sent through custom-bot surface")
            name = node.get("name")
            if not isinstance(name, str) or not name:
                errors.append(f"{path}.name is required")
            elif name in form_names:
                errors.append(f"duplicate form/control name: {name}")
            else:
                form_names.add(name)
        if tag in FORM_INTERACTIVE_TAGS and inside_form:
            name = node.get("name")
            if not isinstance(name, str) or not name:
                errors.append(f"{path}.name is required inside form")
            elif name in form_names:
                errors.append(f"duplicate form/control name: {name}")
            else:
                form_names.add(name)
        if tag in {"input", "select_static", "multi_select_static", "select_person", "multi_select_person", "date_picker", "picker_time", "picker_datetime", "checker"} and not inside_form:
            if not isinstance(node.get("name"), str) or not node.get("name"):
                errors.append(f"{path}.name is required")
        if tag in {"select_static", "multi_select_static", "overflow"}:
            options = node.get("options")
            if not isinstance(options, list) or not options:
                errors.append(f"{path}.options must be a non-empty array")
        if tag == "person" and not isinstance(node.get("user_id"), str):
            errors.append(f"{path}.user_id is required")
        if tag == "person_list" and (not isinstance(node.get("persons"), list) or not node.get("persons")):
            errors.append(f"{path}.persons must be a non-empty array")
        if tag == "interactive_container":
            if not isinstance(node.get("elements"), list) or not node.get("elements"):
                errors.append(f"{path}.elements must be a non-empty array")
            if "border" in node:
                errors.append(f"{path}.border is not a Card 2.0 interactive_container field; use has_border/border_color")
            if node.get("has_border") is not None and not isinstance(node.get("has_border"), bool):
                errors.append(f"{path}.has_border must be boolean")
            if node.get("border_color") is not None and not isinstance(node.get("border_color"), str):
                errors.append(f"{path}.border_color must be a string")
            behaviors = node.get("behaviors")
            if not isinstance(behaviors, list) or len(behaviors) != 1 or not isinstance(behaviors[0], dict):
                errors.append(f"{path}.behaviors must contain exactly one behavior")
            else:
                behavior = behaviors[0]
                behavior_type = behavior.get("type")
                if behavior_type == "open_url":
                    url = behavior.get("default_url")
                    if not isinstance(url, str) or not url_like(url):
                        errors.append(f"{path} open_url must contain an http(s)/lark/feishu URL")
                    elif is_placeholder(url):
                        stats["placeholders"] += 1
                        if allow_placeholders:
                            warnings.append(f"{path} URL is a placeholder")
                        else:
                            errors.append(f"{path} URL is still a placeholder")
                elif behavior_type == "callback":
                    stats["callbacks"] += 1
                    if surface == "custom-bot":
                        errors.append(f"{path} callback cannot be sent through custom-bot surface")
                    value = behavior.get("value")
                    if not isinstance(value, dict) or not isinstance(value.get("action"), str) or not value.get("action"):
                        errors.append(f"{path} callback needs value.action")
                    else:
                        forbidden_key = find_forbidden_callback_key(value)
                        if forbidden_key is not None:
                            errors.append(f"{path} callback value contains forbidden identity/secret field: {forbidden_key}")
                else:
                    errors.append(f"{path} has unsupported behavior type: {behavior_type}")
        if inside_interactive and tag in {"form", "table"}:
            errors.append(f"{path} cannot nest {tag} inside interactive_container")
        if tag in {"table", "chart"}:
            stats["tables" if tag == "table" else "charts"] += 1
            if tag == "table":
                if not isinstance(node.get("columns"), list) or not node.get("columns"):
                    errors.append(f"{path}.columns must be a non-empty array")
                if not isinstance(node.get("rows"), list):
                    errors.append(f"{path}.rows must be an array")
                if stats["tables"] > 5:
                    errors.append("card contains more than five table components")
            if tag == "chart" and not isinstance(node.get("chart_spec"), dict):
                errors.append(f"{path}.chart_spec must be an object")
        if tag == "column_set":
            columns = node.get("columns")
            flex_mode = node.get("flex_mode")
            if not isinstance(columns, list) or not columns:
                errors.append(f"{path}.columns must be a non-empty array")
            elif len(columns) == 1 and flex_mode != "none":
                errors.append(f"{path} has one column but flex_mode is {flex_mode!r}; use flex_mode=none for mobile full width")
            elif len(columns) >= 3:
                column_text_lengths = [visible_text_length(column) for column in columns]
                if max(column_text_lengths, default=0) > 90:
                    warnings.append(f"{path} is a multi-column layout with long text; verify narrow-screen wrapping")
        for key, value in node.items():
            if key == "text_size" and value not in TEXT_SIZES:
                warnings.append(f"{path}.text_size={value!r} is not in the stable style set")
            if key == "text_color" and isinstance(value, str):
                normalized_color = normalize_cardkit_text_color(value)
                if normalized_color not in CARDKIT_TEXT_COLORS:
                    errors.append(f"{path}.text_color invalid CardKit color: {value}")
            if key == "content" and isinstance(value, str) and is_placeholder(value):
                stats["placeholders"] += 1
            visit(
                value,
                f"{path}.{key}",
                depth + (1 if tag in {"column_set", "collapsible_panel", "interactive_container", "form", "action"} else 0),
                inside_form or tag == "form",
                inside_interactive or tag == "interactive_container",
                tag if isinstance(tag, str) else parent_tag,
            )

    visit(body.get("elements"), "body.elements")
    if stats["elements"] > 200:
        errors.append("card contains more than 200 elements; split or collapse long content")
    if stats["max_text_block_chars"] > 220:
        errors.append("a visible text block exceeds 220 characters; keep one concise source-backed point and move full text to source.txt or a real source link")
    if stats["visible_text_chars"] > 900:
        errors.append("visible card text exceeds 900 characters; keep summary, 3-5 key points, metrics/chart, and CTA only")
    if stats["buttons"] > 2:
        warnings.append("more than two buttons will be crowded on mobile; keep one primary and one secondary action")
    if stats["callbacks"] and surface == "application-bot":
        warnings.append("callbacks require an application-bot handler and card.action.trigger subscription")
    if stats["placeholders"] and not allow_placeholders:
        # Specific errors have already been emitted for actionable placeholders;
        # keep the summary useful without duplicating every path.
        warnings.append("placeholder values remain; do not send until replaced")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "stats": stats, "document_format": document_format}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a Feishu Card 2.0 file")
    parser.add_argument("card", help="path to .card JSON")
    parser.add_argument("--surface", choices=sorted(SURFACES), default="raw")
    parser.add_argument("--allow-placeholders", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = Path(args.card).expanduser()
    try:
        raw = path.read_text(encoding="utf-8")
        card = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)], "warnings": [], "stats": {}}, ensure_ascii=False, indent=2))
        return 2
    result = validate(card, surface=args.surface, allow_placeholders=args.allow_placeholders)
    result["stats"]["bytes"] = len(raw.encode("utf-8"))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
