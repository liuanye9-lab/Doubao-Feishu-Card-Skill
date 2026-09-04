#!/usr/bin/env python3
"""Small, confirmation-gated Feishu CLI adapter for the 豆包工作 card Skill.

It deliberately uses argv lists and stdin JSON instead of a shell command so
card content and paths cannot be interpreted as shell syntax. All remote
writes are opt-in and have a dry-run path. CardKit template import is exposed
as ``push-cardkit``; the older ``create-cardkit`` remains the explicit API
Card Entity path.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from validate_card import validate  # noqa: E402
from cardkit_format import derive_card_name, extract_dsl, normalize_dsl  # noqa: E402
from runtime_profile import image_mode_config, supported_image_modes  # noqa: E402


def _cli_candidates(name: str, env_var: str) -> list:
    """PATH first, then an env override, then the common per-user install dir."""
    candidates = [shutil.which(name), os.environ.get(env_var)]
    candidates.append(str(Path.home() / ".local" / "bin" / name))
    return candidates


def _find_lark_cli() -> str:
    for candidate in _cli_candidates("lark-cli", "LARK_CLI_BIN"):
        if candidate and Path(candidate).exists():
            return candidate
    raise RuntimeError("lark-cli not found in PATH; install/configure lark-cli before using remote actions")


def _find_byted_cli() -> str:
    for candidate in _cli_candidates("bytedcli", "BYTED_CLI_BIN"):
        if candidate and Path(candidate).exists():
            return candidate
    raise RuntimeError("bytedcli not found in PATH; install/configure the Feishu CardKit adapter before using direct import")


def _cli_env() -> Dict[str, str]:
    env = dict(os.environ)
    env["LARKSUITE_CLI_NO_UPDATE_NOTIFIER"] = "1"
    env["LARKSUITE_CLI_NO_SKILLS_NOTIFIER"] = "1"
    return env


def _decode_json(raw: str) -> Optional[Any]:
    value = raw.strip()
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        start = value.find("{")
        if start < 0:
            return None
        try:
            decoded, _ = json.JSONDecoder().raw_decode(value[start:])
            return decoded
        except json.JSONDecodeError:
            return None


def _run_cli(args: Sequence[str], *, stdin: Optional[str] = None, dry_run: bool = False) -> Tuple[int, Any, str]:
    command = [_find_lark_cli(), *args]
    if dry_run and "--dry-run" not in command:
        command.append("--dry-run")
    process = subprocess.run(
        command,
        cwd=ROOT,
        input=stdin,
        text=True,
        capture_output=True,
        env=_cli_env(),
        check=False,
    )
    payload = _decode_json(process.stdout) or _decode_json(process.stderr)
    detail = "\n".join(part for part in (process.stdout.strip(), process.stderr.strip()) if part).strip()
    return process.returncode, payload, detail


def _run_byted_cli(args: Sequence[str], *, dry_run: bool = False) -> Tuple[int, Any, str]:
    """Run Byte CLI's Web-backed Feishu surface with machine-readable output."""
    command = [_find_byted_cli(), "-j", *args]
    if dry_run and "--dry-run" not in command:
        command.append("--dry-run")
    process = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=_cli_env(),
        check=False,
    )
    payload = _decode_json(process.stdout) or _decode_json(process.stderr)
    detail = "\n".join(part for part in (process.stdout.strip(), process.stderr.strip()) if part).strip()
    return process.returncode, payload, detail


def _path_from_user(value: str) -> Path:
    raw = Path(value).expanduser()
    if raw.is_absolute():
        path = raw.resolve()
    else:
        current_path = raw.resolve()
        try:
            current_path.relative_to(ROOT)
            path = current_path
        except ValueError:
            path = (ROOT / raw).resolve()
    try:
        path.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError(f"lark-cli 只接受 Skill 目录内的相对文件；请先把文件复制到 {ROOT} 内: {path}") from exc
    return path


def _relative_for_cli(path: Path) -> str:
    return "./" + path.relative_to(ROOT).as_posix()


def _card_from_path(value: str) -> Tuple[Path, Dict[str, Any], Dict[str, Any]]:
    path = _path_from_user(value)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取 Card JSON: {path}: {exc}") from exc
    try:
        card, _, _ = extract_dsl(document)
        card, _ = normalize_dsl(card)
    except ValueError as exc:
        raise ValueError(f"无法解析 CardKit/ Card JSON: {path}: {exc}") from exc
    surface = "application-bot" if _count_callbacks(card) else "raw"
    validation = validate(card, surface=surface)
    if not validation.get("ok"):
        raise ValueError("Card JSON 2.0 校验失败: " + "; ".join(validation.get("errors", [])))
    return path, card, validation


def _image_readiness_gate(path: Path) -> Optional[Dict[str, Any]]:
    """Block remote use of the default draft until its required hero is ready."""
    candidates = [path.with_suffix(".report.json")]
    if path.name.endswith(".cardkit.card"):
        candidates.append(path.with_name(path.name[:-len(".cardkit.card")] + ".report.json"))
    elif path.name.endswith(".cardkit.json"):
        candidates.append(path.with_name(path.name[:-len(".cardkit.json")] + ".report.json"))
    report_path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if report_path is None:
        return None
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    doubao = report.get("doubao") if isinstance(report, dict) else None
    readiness = report.get("readiness") if isinstance(report, dict) else None
    if not isinstance(doubao, dict) or not isinstance(readiness, dict):
        return None
    if bool(doubao.get("image_required")) and not bool(readiness.get("image_ready")):
        dynamic = bool(doubao.get("seedance_required"))
        return {
            "status": "image_required",
            "message": (
                "该卡片报告仍要求 Seedance 2.5 直出的 hero.gif；请先生成、登记并上传 GIF，获得真实 image_key 后重新编译。"
                if dynamic
                else "该卡片报告仍要求 Seedream 5.0 Pro 直出的 hero.png；请先生成、登记并上传图片，获得真实 image_key 后重新编译。"
            ),
            "card": str(path),
            "report": str(report_path),
        }
    return None


def _image_upload_gate(path: Path) -> Optional[Dict[str, Any]]:
    """Allow only a verified Seedream image or direct Seedance GIF."""
    if path.name == "hero.png":
        provenance_path = path.with_name("hero-generation.json")
        if provenance_path.is_file():
            try:
                provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                return {
                    "ok": False,
                    "status": "visual_provenance_invalid",
                    "message": f"Seedream 5.0 Pro 生成溯源文件无法读取: {exc}",
                    "image": str(path),
                    "provenance": str(provenance_path),
                }
            text_policy = str(provenance.get("text_policy") or "").strip() if isinstance(provenance, dict) else ""
            generation_mode = str(provenance.get("generation_mode") or "").strip() if isinstance(provenance, dict) else ""
            if not generation_mode:
                generation_mode = next(
                    (
                        candidate
                        for candidate in supported_image_modes()
                        if image_mode_config(candidate).get("text_policy") == text_policy
                    ),
                    "",
                )
            mode_policy_ok = bool(
                generation_mode in supported_image_modes()
                and text_policy == image_mode_config(generation_mode).get("text_policy")
            )
            if mode_policy_ok:
                image_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
                family = str(provenance.get("generation_family") or "").strip().lower()
                tool = str(provenance.get("tool") or "").strip()
                prompt_value = Path(str(provenance.get("prompt_file") or ""))
                prompt_file = prompt_value if prompt_value.is_absolute() else path.parent / prompt_value
                prompt_hash_ok = True
                if provenance.get("prompt_sha256") and prompt_file.is_file():
                    prompt_hash_ok = provenance.get("prompt_sha256") == hashlib.sha256(prompt_file.read_bytes()).hexdigest()
                valid = (
                    family.startswith("seedream")
                    and (tool in {"doubao.image_gen", "image_gen", "seedream"} or tool.endswith(".image_gen"))
                    and provenance.get("image_sha256") == image_sha256
                    and prompt_file.is_file()
                    and prompt_hash_ok
                )
                if valid:
                    return None
                return {
                    "ok": False,
                    "status": "visual_provenance_failed",
                    "message": "hero.png 的 Seedream 5.0 Pro 直出溯源、模式、文件哈希或提示词哈希校验失败，不能上传。",
                    "image": str(path),
                    "provenance": str(provenance_path),
                }
        return {
            "ok": False,
            "status": "visual_provenance_missing",
            "message": "hero.png 没有被登记为 Doubao Seedream 5.0 Pro 一次性完整卡片图片资产（当前模式可为竖版或横幅）；必须先生成图片分工清单中的图片并登记匹配的 generation_mode/text_policy。",
            "image": str(path),
            "provenance": str(provenance_path),
        }
    if path.name == "hero.gif":
        provenance_path = path.with_name("hero-motion-generation.json")
        if not provenance_path.is_file():
            return {
                "ok": False,
                "status": "motion_provenance_missing",
                "message": "hero.gif 缺少 Seedance 2.5 直出溯源；必须先运行 register_motion_generation.py。",
                "image": str(path),
                "provenance": str(provenance_path),
            }
        try:
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "ok": False,
                "status": "motion_provenance_invalid",
                "message": f"Seedance 2.5 GIF 溯源文件无法读取: {exc}",
                "image": str(path),
                "provenance": str(provenance_path),
            }
        prompt_value = Path(str(provenance.get("prompt_file") or "")) if isinstance(provenance, dict) else Path()
        prompt_file = prompt_value if prompt_value.is_absolute() else path.parent / prompt_value
        prompt_hash_ok = bool(prompt_file.is_file())
        if prompt_hash_ok and provenance.get("prompt_sha256"):
            prompt_hash_ok = provenance.get("prompt_sha256") == hashlib.sha256(prompt_file.read_bytes()).hexdigest()
        family = str(provenance.get("generation_family") or "").strip().lower() if isinstance(provenance, dict) else ""
        tool = str(provenance.get("tool") or "").strip() if isinstance(provenance, dict) else ""
        inspection = provenance.get("inspection") if isinstance(provenance, dict) and isinstance(provenance.get("inspection"), dict) else {}
        valid = bool(
            path.read_bytes()[:6] in {b"GIF87a", b"GIF89a"}
            and family.startswith("seedance")
            and (tool in {"doubao.video_gen", "video_gen", "motion_gen", "animation_gen"} or tool.endswith((".video_gen", ".motion_gen", ".animation_gen")))
            and provenance.get("asset_sha256") == hashlib.sha256(path.read_bytes()).hexdigest()
            and provenance.get("asset_name") == "hero.gif"
            and str(provenance.get("output_format") or "").lower() == "gif"
            and bool(inspection.get("animated"))
            and int(inspection.get("frame_count") or 0) >= 2
            and prompt_hash_ok
        )
        if valid:
            return None
        return {
            "ok": False,
            "status": "motion_provenance_failed",
            "message": "hero.gif 的 Seedance 2.5 直出模型、GIF 帧、文件哈希或提示词哈希校验失败，不能上传。",
            "image": str(path),
            "provenance": str(provenance_path),
        }
    return None


def _count_callbacks(node: Any) -> int:
    if isinstance(node, dict):
        count = 1 if node.get("type") == "callback" else 0
        return count + sum(_count_callbacks(value) for value in node.values())
    if isinstance(node, list):
        return sum(_count_callbacks(value) for value in node)
    return 0


def _value_from(payload: Any, *paths: Tuple[str, ...]) -> Any:
    for path in paths:
        value = payload
        for part in path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(part)
        if value not in (None, ""):
            return value
    return None


def _byted_ok(code: int, payload: Any) -> bool:
    if code != 0 or not isinstance(payload, dict):
        return False
    if payload.get("error") not in (None, "", False):
        return False
    if payload.get("ok") is False:
        return False
    status = str(payload.get("status") or "").strip().lower()
    return status not in {"error", "failed", "failure"}


def _template_candidates(value: Any) -> list[Dict[str, Any]]:
    candidates: list[Dict[str, Any]] = []
    if isinstance(value, dict):
        template_id = _value_from(value, ("template_id",), ("templateId",), ("id",))
        template_name = _value_from(value, ("name",), ("template_name",), ("templateName",), ("title",))
        if template_id not in (None, ""):
            candidates.append({"template_id": str(template_id), "name": str(template_name or "")})
        for nested in value.values():
            candidates.extend(_template_candidates(nested))
    elif isinstance(value, list):
        for nested in value:
            candidates.extend(_template_candidates(nested))
    return candidates


def _template_id_from(payload: Any) -> Optional[str]:
    direct = _value_from(
        payload,
        ("data", "result", "card_id"),
        ("data", "result", "template_id"),
        ("data", "template_id"),
        ("data", "templateId"),
        ("data", "card_id"),
        ("template_id",),
        ("templateId",),
        ("card_id",),
    )
    if direct not in (None, ""):
        return str(direct)
    candidates = _template_candidates(payload)
    return candidates[0]["template_id"] if candidates else None


def _template_list_matches(payload: Any, template_id: str, card_name: str) -> bool:
    expected_id = str(template_id)
    expected_name = str(card_name).strip()
    for candidate in _template_candidates(payload):
        if candidate.get("template_id") != expected_id:
            continue
        candidate_name = str(candidate.get("name") or "").strip()
        if candidate_name and candidate_name != expected_name:
            continue
        return True
    return False


def _whoami(identity: str) -> Tuple[bool, Any, str]:
    code, payload, detail = _run_cli(["whoami", "--as", identity])
    ok = code == 0 and isinstance(payload, dict) and bool(payload.get("available"))
    return ok, payload, detail


def _record(path_value: Optional[str], result: Dict[str, Any]) -> None:
    if not path_value:
        return
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def upload_image(
    image: str,
    *,
    identity: str = "bot",
    confirm: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    path = _path_from_user(image)
    if not path.is_file():
        raise ValueError(f"image file not found: {path}")
    if not dry_run and not confirm:
        return {
            "ok": False,
            "status": "confirmation_required",
            "message": "上传图片是远程写入，请先确认图片、身份和目标，再加 --confirm。",
            "image": str(path),
            "identity": identity,
        }
    image_gate = _image_upload_gate(path)
    if image_gate:
        return {**image_gate, "identity": identity}
    args = [
        "im", "images", "create",
        "--as", identity,
        "--data", '{"image_type":"message"}',
        "--file", f"image={_relative_for_cli(path)}",
        "--format", "json",
    ]
    code, payload, detail = _run_cli(args, dry_run=dry_run)
    ok = code == 0 and isinstance(payload, dict) and payload.get("ok") is True
    image_key = _value_from(payload, ("data", "image_key"), ("image_key",))
    result = {
        "ok": ok,
        "status": "preview_only" if dry_run and ok else ("image_ready" if ok and image_key else "failed"),
        "image": str(path),
        "image_key": image_key,
        "identity": identity,
        "cli": "lark-cli im images create",
        "detail": None if ok else detail[-2000:],
    }
    return result


def create_cardkit(
    card_value: str,
    *,
    identity: str = "bot",
    confirm: bool = False,
    dry_run: bool = False,
    record: Optional[str] = None,
) -> Dict[str, Any]:
    path, card, validation = _card_from_path(card_value)
    if identity == "user":
        result = {
            "ok": False,
            "status": "unsupported_identity",
            "message": "CardKit 创建接口要求应用 tenant_access_token；当前 user access token 不支持该接口，请改用 --as bot。",
            "card": str(path),
            "identity": identity,
        }
        _record(record, result)
        return result
    image_gate = _image_readiness_gate(path)
    if image_gate:
        result = {"ok": False, **image_gate, "identity": identity}
        _record(record, result)
        return result
    if not dry_run and not confirm:
        result = {
            "ok": False,
            "status": "confirmation_required",
            "message": "创建 CardKit Card Entity 是远程写入，请加 --confirm 明确授权。",
            "card": str(path),
            "identity": identity,
        }
        _record(record, result)
        return result
    request = {"type": "card_json", "data": json.dumps(card, ensure_ascii=False, separators=(",", ":"))}
    code, payload, detail = _run_cli(
        [
            "api", "POST", "/open-apis/cardkit/v1/cards",
            "--as", identity,
            "--data", "-",
            "--format", "json",
        ],
        stdin=json.dumps(request, ensure_ascii=False),
        dry_run=dry_run,
    )
    ok = code == 0 and isinstance(payload, dict) and payload.get("ok") is True
    card_id = _value_from(payload, ("data", "card_id"), ("card_id",))
    result = {
        "ok": ok,
        "status": "preview_only" if dry_run and ok else ("cardkit_entity_created" if ok and card_id else "failed"),
        "card": str(path),
        "identity": identity,
        "card_id": card_id,
        "validation": validation,
        "editor_url": "https://open.larkoffice.com/cardkit",
        "cli": "lark-cli api POST /open-apis/cardkit/v1/cards",
        "detail": None if ok else detail[-3000:],
    }
    _record(record, result)
    return result


def push_cardkit(
    card_value: str,
    *,
    name: Optional[str] = None,
    confirm: bool = False,
    dry_run: bool = False,
    record: Optional[str] = None,
) -> Dict[str, Any]:
    """Import a raw Card 2.0 file into CardKit's editable template surface.

    This is deliberately separate from ``create_cardkit``: the latter calls
    the CardKit API Card Entity endpoint, while this command uses Byte CLI's
    Web-backed ``template import`` and verifies the resulting template.  A
    CardKit web wrapper is rejected here so the two file dialects stay
    explicit; the browser fallback consumes that wrapper instead.
    """
    path = _path_from_user(card_value)
    if path.name.endswith(".cardkit.card") or path.name.endswith(".cardkit.json"):
        result = {
            "ok": False,
            "status": "unsupported_input",
            "message": "直接 CardKit CLI 导入需要裸 Card 2.0 文件；.cardkit.card/.cardkit.json wrapper 请走已登录浏览器导入。",
            "card": str(path),
            "cli": "bytedcli -j feishu cardkit template import",
        }
        _record(record, result)
        return result

    path, card, validation = _card_from_path(card_value)
    image_gate = _image_readiness_gate(path)
    if image_gate:
        result = {"ok": False, **image_gate}
        _record(record, result)
        return result

    card_name = str(name or derive_card_name(card, path.stem)).strip() or "card"
    if not dry_run and not confirm:
        result = {
            "ok": False,
            "status": "confirmation_required",
            "message": "导入 CardKit 模板是远程写入，请确认卡片、名称和登录会话后加 --confirm。",
            "card": str(path),
            "card_name": card_name,
            "cli": "bytedcli -j feishu cardkit template import",
        }
        _record(record, result)
        return result

    import_args = [
        "feishu", "cardkit", "template", "import",
        "--file", _relative_for_cli(path),
        "--name", card_name,
    ]
    code, payload, detail = _run_byted_cli(import_args, dry_run=dry_run)
    import_ok = _byted_ok(code, payload)
    template_id = _template_id_from(payload)
    result: Dict[str, Any] = {
        "ok": import_ok,
        "status": "preview_only" if dry_run and import_ok else "failed",
        "card": str(path),
        "card_name": card_name,
        "template_id": template_id,
        "validation": validation,
        "cli": "bytedcli -j feishu cardkit template import",
        "detail": None if import_ok else detail[-3000:],
    }
    if dry_run:
        _record(record, result)
        return result
    if not import_ok:
        _record(record, result)
        return result
    if not template_id:
        result.update({
            "ok": False,
            "status": "cardkit_import_unverified",
            "message": "CardKit 导入命令返回成功但没有 template_id，不能声明模板已落入可编辑资源。",
        })
        _record(record, result)
        return result

    get_code, get_payload, get_detail = _run_byted_cli(
        ["feishu", "cardkit", "template", "get", "--template-id", template_id]
    )
    list_code, list_payload, list_detail = _run_byted_cli(
        [
            "feishu", "cardkit", "template", "list",
            "--source", "mine",
            "--status", "all",
            "--page", "1",
            "--page-size", "100",
            "--sort", "updated",
        ]
    )
    get_ok = _byted_ok(get_code, get_payload)
    list_ok = _byted_ok(list_code, list_payload)
    list_match = list_ok and _template_list_matches(list_payload, template_id, card_name)
    verified = get_ok and list_match
    result.update({
        "ok": verified,
        "status": "cardkit_imported" if verified else "cardkit_import_unverified",
        "evidence": {
            "template_get_ok": get_ok,
            "template_list_ok": list_ok,
            "template_list_match": list_match,
        },
        "readback": {
            "template_get": get_payload,
            "template_list": list_payload,
        },
        "detail": None if verified else "\n".join(
            part for part in (get_detail[-1500:], list_detail[-1500:]) if part
        ).strip(),
    })
    _record(record, result)
    return result


def send_card(
    card_value: str,
    *,
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None,
    identity: str = "bot",
    confirm: bool = False,
    dry_run: bool = False,
    idempotency_key: Optional[str] = None,
    record: Optional[str] = None,
) -> Dict[str, Any]:
    path, card, validation = _card_from_path(card_value)
    if not chat_id and not user_id:
        raise ValueError("send-card 需要 --chat-id 或 --user-id")
    if chat_id and user_id:
        raise ValueError("--chat-id 与 --user-id 不能同时使用")
    image_gate = _image_readiness_gate(path)
    if image_gate:
        result = {"ok": False, **image_gate, "identity": identity, "chat_id": chat_id, "user_id": user_id}
        _record(record, result)
        return result
    if not dry_run and not confirm:
        result = {
            "ok": False,
            "status": "confirmation_required",
            "message": "发送消息是对外动作，请先确认收件人、内容和身份，再加 --confirm。",
            "card": str(path),
            "identity": identity,
            "chat_id": chat_id,
            "user_id": user_id,
        }
        _record(record, result)
        return result
    args = [
        "im", "+messages-send",
        "--as", identity,
        "--msg-type", "interactive",
        "--content", json.dumps(card, ensure_ascii=False, separators=(",", ":")),
        "--format", "json",
    ]
    args += ["--chat-id", chat_id] if chat_id else ["--user-id", user_id or ""]
    if idempotency_key:
        args += ["--idempotency-key", idempotency_key]
    code, payload, detail = _run_cli(args, dry_run=dry_run)
    ok = code == 0 and isinstance(payload, dict) and payload.get("ok") is True
    message_id = _value_from(payload, ("data", "message_id"), ("message_id",))
    result = {
        "ok": ok,
        "status": "preview_only" if dry_run and ok else ("sent" if ok and message_id else "failed"),
        "card": str(path),
        "identity": identity,
        "chat_id": chat_id,
        "user_id": user_id,
        "message_id": message_id,
        "validation": validation,
        "cli": "lark-cli im +messages-send",
        "detail": None if ok else detail[-3000:],
    }
    _record(record, result)
    return result


def preview_card(
    card_value: str,
    *,
    identity: str = "bot",
    confirm: bool = False,
    dry_run: bool = False,
    idempotency_key: Optional[str] = None,
    record: Optional[str] = None,
) -> Dict[str, Any]:
    """Send a bot preview to the currently authenticated user's own chat."""
    path, card, validation = _card_from_path(card_value)
    if identity != "bot":
        result = {
            "ok": False,
            "status": "unsupported_identity",
            "message": "Bot 预览必须使用应用 Bot 身份；不要用 user 身份替代。",
            "card": str(path),
            "identity": identity,
        }
        _record(record, result)
        return result
    image_gate = _image_readiness_gate(path)
    if image_gate:
        result = {"ok": False, **image_gate, "identity": identity}
        _record(record, result)
        return result
    if not dry_run and not confirm:
        result = {
            "ok": False,
            "status": "confirmation_required",
            "message": "向当前飞书账号发送 Bot 预览是远程写入，请加 --confirm 明确授权。",
            "card": str(path),
            "identity": identity,
            "preview_target": "current_user",
        }
        _record(record, result)
        return result

    bot_ok, _, bot_detail = _whoami("bot")
    if not bot_ok:
        result = {
            "ok": False,
            "status": "bot_required",
            "message": "未检测到可用的飞书应用 Bot；请先配置 lark-cli Bot 身份和消息发送权限。",
            "card": str(path),
            "identity": identity,
            "detail": bot_detail[-2000:],
        }
        _record(record, result)
        return result

    user_ok, user_payload, user_detail = _whoami("user")
    user_id = _value_from(
        user_payload,
        ("onBehalfOf", "openId"),
        ("on_behalf_of", "open_id"),
        ("openId",),
    )
    if not user_ok or not user_id:
        result = {
            "ok": False,
            "status": "user_required",
            "message": "无法解析当前登录用户的 open_id，Bot 预览需要一个明确的本人会话目标。",
            "card": str(path),
            "identity": identity,
            "preview_target": "current_user",
            "detail": user_detail[-2000:],
        }
        _record(record, result)
        return result

    stable_card = json.dumps(card, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    preview_key = idempotency_key or f"doubao-preview-{hashlib.sha256(stable_card.encode('utf-8')).hexdigest()[:32]}"
    args = [
        "im", "+messages-send",
        "--as", identity,
        "--msg-type", "interactive",
        "--content", stable_card,
        "--user-id", str(user_id),
        "--idempotency-key", preview_key,
        "--format", "json",
    ]
    code, payload, detail = _run_cli(args, dry_run=dry_run)
    ok = code == 0 and isinstance(payload, dict) and payload.get("ok") is True
    message_id = _value_from(payload, ("data", "message_id"), ("message_id",))
    result = {
        "ok": ok,
        "status": "preview_only" if dry_run and ok else ("preview_sent" if ok and message_id else "failed"),
        "card": str(path),
        "identity": identity,
        "preview_target": "current_user",
        "user_id": user_id,
        "message_id": message_id,
        "idempotency_key": preview_key,
        "forwardable": bool(card.get("config", {}).get("enable_forward", True)) if isinstance(card.get("config"), dict) else True,
        "validation": validation,
        "cli": "lark-cli im +messages-send",
        "detail": None if ok else detail[-3000:],
    }
    _record(record, result)
    return result


def record_cardkit_import(
    manifest_value: str,
    *,
    status: str = "pending",
    observed_name: Optional[str] = None,
    editor_opened: bool = False,
    page_url: Optional[str] = None,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist browser evidence without pretending to perform the browser upload."""
    manifest_path = _path_from_user(manifest_value)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取 CardKit 导入清单: {manifest_path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValueError("CardKit 导入清单必须是 JSON object")
    if status not in {"pending", "imported"}:
        raise ValueError("status must be pending or imported")
    card_name = str(manifest.get("card_name") or "").strip()
    if not card_name:
        raise ValueError("CardKit 导入清单缺少 card_name")
    name_visible = bool(observed_name and observed_name.strip() == card_name)
    editor_verified = bool(editor_opened)
    if status == "imported" and not (name_visible and editor_verified):
        return {
            "ok": False,
            "status": "invalid_evidence",
            "message": "只有‘我的卡片’完全匹配名称且编辑页可打开，才能记录 imported。",
            "manifest": str(manifest_path),
            "card_name": card_name,
            "observed_name": observed_name,
            "editor_opened": editor_verified,
        }
    result_status = "imported" if name_visible and editor_verified else "pending"
    result_name = manifest_path.name.replace(".cardkit-import.json", ".cardkit-import-result.json")
    if result_name == manifest_path.name:
        result_name = f"{manifest_path.stem}.cardkit-import-result.json"
    result_path = manifest_path.with_name(result_name)
    result = {
        "ok": True,
        "status": result_status,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "manifest": str(manifest_path),
        "card": manifest.get("card"),
        "card_name": card_name,
        "observed_name": observed_name,
        "page_url": page_url,
        "evidence": {
            "my_cards_name_visible": name_visible,
            "editor_page_openable": editor_verified,
        },
        "note": note,
        "result": str(result_path),
    }
    _record(str(result_path), result)
    return result


def cli_status() -> Dict[str, Any]:
    # Current lark-cli emits machine-readable JSON by default and does not
    # accept a ``--json`` flag. Keep the command literal so this preflight
    # works with the installed CLI instead of failing before auth checks.
    doctor_code, doctor_payload, doctor_detail = _run_cli(["doctor"])
    doctor_ok = doctor_code == 0 and isinstance(doctor_payload, dict) and doctor_payload.get("ok") is not False
    bot_ok, bot_payload, bot_detail = _whoami("bot")
    user_ok, user_payload, user_detail = _whoami("user")
    return {
        "ok": doctor_ok and bot_ok and user_ok,
        "status": "ready" if doctor_ok and bot_ok and user_ok else ("bot_required" if not bot_ok else "user_required" if not user_ok else "cli_required"),
        "identity": "bot",
        "cli": {
            "ok": doctor_ok,
            "doctor": doctor_payload if isinstance(doctor_payload, dict) else None,
        },
        "token_status": bot_payload.get("tokenStatus") if isinstance(bot_payload, dict) else None,
        "on_behalf_of": user_payload.get("onBehalfOf") if isinstance(user_payload, dict) else None,
        "bot": {
            "ok": bot_ok,
            "token_status": bot_payload.get("tokenStatus") if isinstance(bot_payload, dict) else None,
        },
        "user": {
            "ok": user_ok,
            "token_status": user_payload.get("tokenStatus") if isinstance(user_payload, dict) else None,
            "on_behalf_of": user_payload.get("onBehalfOf") if isinstance(user_payload, dict) else None,
        },
        "detail": None if doctor_ok and bot_ok and user_ok else (doctor_detail[-2000:] or bot_detail[-2000:] or user_detail[-2000:]),
        "cli_command": "lark-cli doctor; lark-cli whoami --as bot/user",
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Confirmation-gated Feishu CLI adapter for 豆包工作 cards")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status")
    status.set_defaults(identity="bot")

    upload = sub.add_parser("upload-image")
    upload.add_argument("--image", required=True)
    upload.add_argument("--as", dest="identity", choices=("bot", "user"), default="bot")
    upload.add_argument("--confirm", action="store_true")
    upload.add_argument("--dry-run", action="store_true")

    cardkit = sub.add_parser("create-cardkit")
    cardkit.add_argument("--card", required=True)
    cardkit.add_argument("--as", dest="identity", choices=("bot", "user"), default="bot")
    cardkit.add_argument("--confirm", action="store_true")
    cardkit.add_argument("--dry-run", action="store_true")
    cardkit.add_argument("--record")

    direct_cardkit = sub.add_parser("push-cardkit")
    direct_cardkit.add_argument("--card", required=True)
    direct_cardkit.add_argument("--name")
    direct_cardkit.add_argument("--confirm", action="store_true")
    direct_cardkit.add_argument("--dry-run", action="store_true")
    direct_cardkit.add_argument("--record")

    send = sub.add_parser("send-card")
    send.add_argument("--card", required=True)
    target = send.add_mutually_exclusive_group(required=True)
    target.add_argument("--chat-id")
    target.add_argument("--user-id")
    send.add_argument("--as", dest="identity", choices=("bot", "user"), default="bot")
    send.add_argument("--confirm", action="store_true")
    send.add_argument("--dry-run", action="store_true")
    send.add_argument("--idempotency-key")
    send.add_argument("--record")

    preview = sub.add_parser("preview-card")
    preview.add_argument("--card", required=True)
    preview.add_argument("--as", dest="identity", choices=("bot",), default="bot")
    preview.add_argument("--confirm", action="store_true")
    preview.add_argument("--dry-run", action="store_true")
    preview.add_argument("--idempotency-key")
    preview.add_argument("--record")

    import_result = sub.add_parser("record-cardkit-import")
    import_result.add_argument("--manifest", required=True)
    import_result.add_argument("--status", choices=("pending", "imported"), default="pending")
    import_result.add_argument("--observed-name")
    import_result.add_argument("--editor-opened", action="store_true")
    import_result.add_argument("--page-url")
    import_result.add_argument("--note")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "status":
            result = cli_status()
        elif args.command == "upload-image":
            result = upload_image(args.image, identity=args.identity, confirm=args.confirm, dry_run=args.dry_run)
        elif args.command == "create-cardkit":
            result = create_cardkit(args.card, identity=args.identity, confirm=args.confirm, dry_run=args.dry_run, record=args.record)
        elif args.command == "push-cardkit":
            result = push_cardkit(args.card, name=args.name, confirm=args.confirm, dry_run=args.dry_run, record=args.record)
        elif args.command == "send-card":
            result = send_card(
                args.card,
                chat_id=args.chat_id,
                user_id=args.user_id,
                identity=args.identity,
                confirm=args.confirm,
                dry_run=args.dry_run,
                idempotency_key=args.idempotency_key,
                record=args.record,
            )
        elif args.command == "preview-card":
            result = preview_card(
                args.card,
                identity=args.identity,
                confirm=args.confirm,
                dry_run=args.dry_run,
                idempotency_key=args.idempotency_key,
                record=args.record,
            )
        elif args.command == "record-cardkit-import":
            result = record_cardkit_import(
                args.manifest,
                status=args.status,
                observed_name=args.observed_name,
                editor_opened=args.editor_opened,
                page_url=args.page_url,
                note=args.note,
            )
        else:
            raise ValueError(f"unknown command: {args.command}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") or result.get("status") == "confirmation_required" else 2
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
