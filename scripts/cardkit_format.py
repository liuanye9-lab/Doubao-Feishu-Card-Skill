#!/usr/bin/env python3
"""CardKit file-format adapter shared by the compiler and CLI.

The skill owns two deliberately different artifacts:

* a raw Card 2.0 object for API sends and Bot previews; and
* a ``{"name", "dsl", "variables"}`` envelope for the CardKit web editor.

Keeping the formats explicit prevents a raw API payload from being mistaken
for an editable CardKit resource while retaining backwards compatibility for
existing ``<name>.card`` files.
"""

from __future__ import annotations

import copy
import json
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple


CARDKIT_MAX_BYTES = 300 * 1024
DSL_KEY_ORDER = ("schema", "config", "card_link", "body", "header")
WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{index}" for index in range(0, 10)),
    *(f"lpt{index}" for index in range(0, 10)),
}


def extract_dsl(value: Any) -> Tuple[Dict[str, Any], Optional[str], List[Any]]:
    """Return ``(dsl, wrapper_name, variables)`` from common CardKit inputs.

    The importer Skill accepts raw cards, wrapped ``.card`` files, arrays
    containing either form, and exports where ``dsl`` was serialized as JSON
    text.  This function intentionally does not silently repair content.
    Structural repairs belong to :func:`normalize_dsl` and are reported.
    """
    current = value
    if isinstance(current, list):
        if not current:
            raise ValueError("card document is an empty array")
        current = current[0]
    if not isinstance(current, dict):
        raise ValueError("card document must be a JSON object")

    if "dsl" in current:
        dsl = current.get("dsl")
        if isinstance(dsl, str):
            try:
                dsl = json.loads(dsl)
            except json.JSONDecodeError as exc:
                raise ValueError(f"CardKit wrapper dsl is not valid JSON: {exc}") from exc
        if not isinstance(dsl, dict):
            raise ValueError("CardKit wrapper dsl must be an object or JSON string")
        variables = current.get("variables")
        return dsl, str(current.get("name")) if current.get("name") is not None else None, list(variables) if isinstance(variables, list) else []

    # A few export tools put the raw card below a ``card`` property.  Support
    # that shape without treating arbitrary nested objects as a card.
    nested = current.get("card")
    if isinstance(nested, dict) and ("schema" in nested or "body" in nested):
        return nested, None, []
    return current, None, []


def normalize_dsl(value: Mapping[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Copy a DSL and apply only known CardKit structural normalizations."""
    if not isinstance(value, Mapping):
        raise ValueError("dsl must be an object")
    dsl: Dict[str, Any] = copy.deepcopy(dict(value))
    fixes: List[str] = []

    # CardKit drops custom config.style.color aliases while editing.  Clean
    # legacy references before creating a wrapper so an old card remains
    # editable after import.  New cards use native names in generate_card.py.
    try:
        from validate_card import normalize_cardkit_text_color  # pylint: disable=import-outside-toplevel
    except ModuleNotFoundError:  # package import from the repository root
        from .validate_card import normalize_cardkit_text_color  # type: ignore

    def normalize_legacy_colors(node: Any) -> None:
        if isinstance(node, dict):
            for key, item in list(node.items()):
                if key == "text_color" and isinstance(item, str):
                    normalized = normalize_cardkit_text_color(item)
                    if normalized != item:
                        node[key] = normalized
                        fixes.append(f"normalized legacy text_color {item!r} to {normalized!r}")
                else:
                    normalize_legacy_colors(item)
        elif isinstance(node, list):
            for item in node:
                normalize_legacy_colors(item)

    normalize_legacy_colors(dsl)

    schema = dsl.get("schema")
    if schema in (None, "", 2, 2.0):
        dsl["schema"] = "2.0"
        fixes.append('schema normalized to "2.0"')
    elif not isinstance(schema, str):
        dsl["schema"] = str(schema)
        fixes.append("schema converted to string")

    card_link = dsl.get("card_link")
    if isinstance(card_link, Mapping) and not str(card_link.get("url") or "").strip():
        dsl.pop("card_link", None)
        fixes.append("removed empty card_link")

    config = dsl.get("config")
    if not isinstance(config, dict):
        config = {}
        dsl["config"] = config
        fixes.append("added config object")
    style = config.get("style")
    if isinstance(style, dict) and isinstance(style.get("color"), dict):
        style.pop("color", None)
        fixes.append("removed non-portable custom config.style.color")
        if not style:
            config.pop("style", None)
    if config.get("update_multi") is not True:
        config["update_multi"] = True
        fixes.append("config.update_multi normalized to true")

    ordered: Dict[str, Any] = OrderedDict()
    for key in DSL_KEY_ORDER:
        if key in dsl:
            ordered[key] = dsl[key]
    for key, item in dsl.items():
        if key not in ordered:
            ordered[key] = item
    return dict(ordered), fixes


def derive_card_name(dsl: Mapping[str, Any], fallback: str = "card") -> str:
    header = dsl.get("header")
    if isinstance(header, Mapping):
        title = header.get("title")
        if isinstance(title, Mapping) and str(title.get("content") or "").strip():
            return str(title["content"]).strip()
    return str(fallback or "card").strip() or "card"


def safe_card_name(value: str) -> str:
    """Return a cross-platform CardKit file stem (<=195 characters)."""
    text = str(value or "card")
    # CardKit uses the name as the exported filename.  Preserve Chinese and
    # other readable Unicode while removing control characters and separators.
    text = re.sub(r"[\x00-\x1f\x7f]|[<>:\"/\\|?*]", "_", text)
    text = re.sub(r"_+", "_", text).strip(" .")
    if not text or text.lower().split(".", 1)[0] in WINDOWS_RESERVED:
        return "untitled"
    return text[:195].rstrip(" .") or "untitled"


def wrap_card(dsl: Mapping[str, Any], name: str, variables: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Build the exact CardKit editor envelope."""
    return {
        "name": str(name or "card"),
        "dsl": copy.deepcopy(dict(dsl)),
        "variables": list(variables or []),
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_cardkit_bundle(
    raw_card_path: Path,
    output_dir: Optional[Path] = None,
    *,
    card_name: Optional[str] = None,
    base_name: Optional[str] = None,
    variables: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """Create sidecar CardKit files for an already compiled raw card.

    The raw ``<name>.card`` remains untouched.  Sidecars are named
    ``<name>.cardkit.card`` and ``<name>.cardkit.json`` so callers can see
    which file is for web import and which file is for API/Bot delivery.
    """
    raw_path = Path(raw_card_path).expanduser().resolve()
    if not raw_path.is_file():
        raise ValueError(f"raw Card JSON not found: {raw_path}")
    try:
        source = json.loads(raw_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read raw Card JSON: {raw_path}: {exc}") from exc
    dsl, wrapped_name, wrapped_variables = extract_dsl(source)
    normalized, fixes = normalize_dsl(dsl)
    name = str(card_name or wrapped_name or derive_card_name(normalized, raw_path.stem)).strip() or "card"
    base = safe_card_name(base_name or raw_path.stem.replace(".card", ""))
    destination = Path(output_dir).expanduser().resolve() if output_dir else raw_path.parent
    wrapper = wrap_card(normalized, name, variables if variables is not None else wrapped_variables)
    cardkit_path = destination / f"{base}.cardkit.card"
    json_path = destination / f"{base}.cardkit.json"
    _write_json(cardkit_path, wrapper)
    _write_json(json_path, wrapper)

    # Import lazily so this format helper remains useful to the converter even
    # when a caller only wants structural normalization.
    from validate_card import validate  # pylint: disable=import-outside-toplevel

    validation = validate(normalized, surface="raw")
    size_bytes = cardkit_path.stat().st_size
    return {
        "card_name": name,
        "safe_name": base,
        "raw_card": str(raw_path),
        "cardkit_card": str(cardkit_path),
        "cardkit_json": str(json_path),
        "variables": wrapper["variables"],
        "fixes": fixes,
        "validation": validation,
        "file_size_bytes": size_bytes,
        "max_file_size_bytes": CARDKIT_MAX_BYTES,
        "size_ok": size_bytes <= CARDKIT_MAX_BYTES,
        "wrapper": wrapper,
    }
