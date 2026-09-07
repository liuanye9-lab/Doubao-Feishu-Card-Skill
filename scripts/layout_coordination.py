"""Coordinate media, native copy and actions without changing visual style or facts."""
from __future__ import annotations
import re

VERSION = "content-coordination/1"


def _key(text):
    return re.sub(r"[^\w\u4e00-\u9fff]", "", str(text or ""))


def choose_image_mode(spec, *, explicit_mode, banner_mode):
    """Prefer a compact entrance for notices; preserve explicit modes and rich diagrams."""
    if explicit_mode or not isinstance(spec.get("hero"), dict):
        return
    allocation = (spec.get("information_allocation") or {}).get("image") or {}
    items = allocation.get("include") or []
    rich = sum(item.get("role") in {"metric", "stage"} for item in items if isinstance(item, dict)) >= 3
    scene = spec.get("scene") or (spec.get("information_allocation") or {}).get("scene")
    if scene not in {"training-notice", "event-info", "prelaunch-promo"} or rich:
        return
    media = spec["analysis"]["design_plan"]["media_policy"]
    media["image_generation_mode"] = banner_mode
    spec["image_generation_mode"] = banner_mode
    spec["hero"]["image_generation_mode"] = banner_mode
    spec["analysis"].setdefault("decision_log", []).append({
        "component": "image_layout", "decision": "applied",
        "reason": "通知用轻量横幅衔接原生模块；保留 preset、字体、色板和模型，不替换视觉风格",
    })


def _bind_actions(spec):
    """Bind only an unambiguous source heading interval; never guess from similar labels."""
    blocks = spec.get("blocks") or []
    lines = str((spec.get("analysis") or {}).get("source_text") or "").splitlines()
    # Highlighted sections are still real source modules.  They must remain
    # eligible owners for their own verified URLs/actions; the old exclusion
    # made the new highlight-first text policy detach buttons to the footer.
    sections = {index: block for index, block in enumerate(blocks)
                if isinstance(block, dict) and block.get("type") == "section"}
    heading_keys = {}
    for index, block in sections.items():
        key = _key(block.get("title"))
        if key:
            heading_keys[key] = None if key in heading_keys else index
    headings = []
    for number, line in enumerate(lines):
        key = _key(line)
        if key in heading_keys:
            headings.append((number, heading_keys[key]))
        elif re.match(r"^\s*#{1,6}\s+", line):
            headings.append((number, None))  # An omitted module is a boundary, not another module's CTA.
    bindings = []
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") != "buttons":
            continue
        remaining = []
        for action in block.get("items", []):
            url = str(action.get("url") or "")
            occurrences = [number for number, line in enumerate(lines) if url and url in line]
            owner = None
            global_action = action.get("placement") == "global" or bool(re.search(r"全部|总览|所有|回顾", str(action.get("text") or "")))
            if len(occurrences) == 1 and not global_action:
                prior = [(number, index) for number, index in headings if number < occurrences[0]]
                if prior:
                    owner = prior[-1][1]
            if owner is None:
                remaining.append(action)
            else:
                sections[owner].setdefault("actions", []).append(action)
                # Remove only the exact source CTA residue after the URL was moved to the button.
                residue = lines[occurrences[0]].replace(url, "").strip(" ：:")
                section = sections[owner]
                if isinstance(section.get("body"), str):
                    section["body"] = "\n".join(line for line in section["body"].splitlines()
                                                if _key(line) not in {_key(residue), _key(action.get("text"))})
                bindings.append({"url": url, "module_title": sections[owner].get("title"),
                                 "source_line": occurrences[0] + 1, "evidence": "exact source heading interval"})
        block["items"] = remaining
    spec["blocks"] = [b for b in blocks if not (b.get("type") == "buttons" and not b.get("items"))]
    return bindings


def coordinate_layout(spec, *, banner=False):
    """Run once during fresh generation; resume renders saved user choices unchanged."""
    if spec.get("layout_coordination", {}).get("version") == VERSION:
        return
    hero = spec.get("hero")
    if isinstance(hero, dict):
        hero.setdefault("scale_type", "fit_horizontal")
        hero.setdefault("size", "stretch")
        hero.setdefault("corner_radius", "8px")
    bindings = _bind_actions(spec)
    for block in spec.get("blocks", []):
        if block.get("type") == "section":
            block.setdefault("coordinated", True)
            block.setdefault("module_padding", "0px")
            block.setdefault("module_spacing", "4px")
            block.setdefault("module_margin", "8px 0px 0px 0px")
    # The banner has a small information job; don't cram a portrait whitelist into it.
    allocation = spec.get("information_allocation") or {}
    image = allocation.get("image") or {}
    if banner and image.get("use"):
        included = image.get("include") or []
        titles = [item for item in included if item.get("role") == "title"][:1]
        priority = {"metric": 0, "fact": 1, "stage": 2, "relationship": 3, "quote": 4}
        candidates = [item for item in included if item.get("role") != "title" and item.get("source_lines") and len(str(item.get("text") or "")) <= 22]
        short = sorted(candidates, key=lambda item: priority.get(item.get("role"), 5))[:2]
        if any(item.get("role") == "metric" for item in short):
            short = [next(item for item in short if item.get("role") == "metric")]  # One focal stat fits a mobile banner.
        selected = titles + short
        if titles:
            image["deferred_to_native_or_source"] = [item for item in included if item not in selected]
            image["include"] = selected
            image["job"] = "横幅突出一个来源重点；详细指标和行动在原生模块"
            image["text_budget"] = "一个标题和一个焦点指标，或最多两个短标签；不得缩小标签"
            media = spec.get("analysis", {}).get("design_plan", {}).get("media_policy", {})
            image["text_policy"] = media.get("text_in_image") or image.get("text_policy")
            media.update(aspect_ratio="3:1", visual_job=image["job"],
                         composition="full-width title row, then one legible focal-fact row",
                         visual_layout="compact-banner-with-native-modules")
            contract = spec.get("visual_contract")
            if isinstance(contract, dict):
                contract.update(job=image["job"], composition=media["composition"],
                                source_spans=[item["text"] for item in selected])
            native = allocation.get("native_card") or {}
            if isinstance(native, dict) and isinstance(native.get("source_lines"), list):
                source_lines = str(spec.get("analysis", {}).get("source_text") or "").splitlines()
                selected_lines = set()
                for item in selected:
                    for source in item.get("source_lines", []):
                        if isinstance(source, int):
                            selected_lines.add(source)
                        else:
                            selected_lines.update(number for number, line in enumerate(source_lines, 1) if _key(line) == _key(source))
                native["image_excluded_source_lines"] = [line for line in native["source_lines"] if line not in selected_lines]
            labels = selected
            for target in [hero, spec.get("visual_contract"), (spec.get("analysis", {}).get("design_plan", {}).get("media_policy"))]:
                if isinstance(target, dict):
                    target["functional_text"] = labels
                    target["information_allocation"] = allocation
    if banner:
        for block in spec.get("blocks", []):
            if block.get("type") in {"metrics", "facts"}:
                block.setdefault("compact", True)
    lead = _key(spec.get("lead"))
    if lead:
        intro = next((b for b in spec.get("blocks", []) if b.get("type") == "text" and _key(b.get("content")) == lead), None)
        if intro is not None:
            spec["blocks"] = [intro] + [b for b in spec["blocks"] if b is not intro]
    spec.setdefault("body_padding", "18px 18px 24px 18px")
    spec.setdefault("vertical_spacing", "12px")
    spec["layout_coordination"] = {
        "version": VERSION, "style_preserved": spec.get("template_id") or spec.get("preset"),
        "image_layout": "banner-led" if banner else "infographic-led" if hero else "native-only",
        "reading_order": ["visual entrance", "concise context", "native modules with local actions", "global action if supplied"],
        "spacing": {"within_module": "4px", "between_modules": "16px", "outer_inset": "12px"},
        "action_bindings": bindings,
        "image_fit": "preserve complete text and diagram",
        "manual_review": ["media/native seam", "CTA ownership", "360px and desktop readability", "no duplicate long copy"],
    }
