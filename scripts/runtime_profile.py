#!/usr/bin/env python3
"""Shared runtime profile for the Doubao Feishu Card image adapter.

The profile deliberately separates a user-requested model profile from
observable host provenance.  ``generation_model`` is the configured Doubao
profile (Seedream 5.0 Pro); a real generation manifest may still use
``platform-managed`` when the host does not expose a model id.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PROFILE_PATH = ROOT / "presets" / "runtime-profile.json"


def load_runtime_profile() -> Dict[str, Any]:
    """Load and minimally validate the Doubao runtime adapter profile."""
    try:
        profile = json.loads(RUNTIME_PROFILE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"runtime profile is unavailable: {RUNTIME_PROFILE_PATH}") from exc
    if not isinstance(profile, dict):
        raise ValueError("runtime profile must be an object")
    image = profile.get("image")
    modes = profile.get("image_modes")
    motion = profile.get("motion")
    motion_modes = profile.get("motion_modes")
    if not isinstance(image, dict) or not isinstance(modes, dict) or not modes:
        raise ValueError("runtime profile must contain image and image_modes objects")
    if not isinstance(motion, dict) or not isinstance(motion_modes, dict) or not motion_modes:
        raise ValueError("runtime profile must contain motion and motion_modes objects")
    return profile


def image_runtime(profile: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Return the image section as a mutable, shallow-independent mapping."""
    value = (profile or load_runtime_profile()).get("image")
    return dict(value) if isinstance(value, Mapping) else {}


def image_mode_config(mode: str, profile: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Return one image mode config, raising for an unknown mode."""
    value = (profile or load_runtime_profile()).get("image_modes")
    if not isinstance(value, Mapping) or not isinstance(value.get(mode), Mapping):
        raise ValueError(f"unsupported Doubao image generation mode: {mode}")
    return dict(value[mode])


def default_image_mode(profile: Optional[Mapping[str, Any]] = None) -> str:
    image = image_runtime(profile)
    mode = str(image.get("default_mode") or "").strip()
    if not mode:
        raise ValueError("runtime profile is missing image.default_mode")
    return mode


def supported_image_modes(profile: Optional[Mapping[str, Any]] = None) -> tuple[str, ...]:
    value = (profile or load_runtime_profile()).get("image_modes")
    if not isinstance(value, Mapping):
        return ()
    return tuple(str(key) for key in value if str(key).strip())


def motion_runtime(profile: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Return the Seedance motion section."""
    value = (profile or load_runtime_profile()).get("motion")
    return dict(value) if isinstance(value, Mapping) else {}


def motion_mode_config(mode: str, profile: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Return one motion-mode config, raising for an unknown mode."""
    value = (profile or load_runtime_profile()).get("motion_modes")
    if not isinstance(value, Mapping) or not isinstance(value.get(mode), Mapping):
        raise ValueError(f"unsupported Doubao motion generation mode: {mode}")
    return dict(value[mode])


def default_motion_mode(profile: Optional[Mapping[str, Any]] = None) -> str:
    motion = motion_runtime(profile)
    mode = str(motion.get("default_mode") or "").strip()
    if not mode:
        raise ValueError("runtime profile is missing motion.default_mode")
    return mode


def supported_motion_modes(profile: Optional[Mapping[str, Any]] = None) -> tuple[str, ...]:
    value = (profile or load_runtime_profile()).get("motion_modes")
    if not isinstance(value, Mapping):
        return ()
    return tuple(str(key) for key in value if str(key).strip())
