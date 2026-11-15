#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""k12100.com 校考成绩与错题安全凭据管理及拟人化同步工具（严格防封号 + 宿主机隔离）。

所有账号密码、浏览器 Profile、探测快照及去重索引一律保存于仓库之外的
`~/.config/shutong/`（目录 0700、文件 0600），绝不进入 Git 工作区。

子命令：
  1. init-credentials : 交互或命令行安全写入 k12100 账号及可选 DEEPSEEK_API_KEY 到 ~/.config/shutong/k12100.env（0600）
  2. config-deepseek  : 单独配置、更新或清空 DEEPSEEK_API_KEY / Base URL / 模型（支持 --from-shell 与 --sync-dev-env）
  3. status           : 校对目录/凭据权限、DeepSeek 密钥状态与本地同步台账
  4. probe            : 打开可见 Chromium 浏览器，低频探测并保存脱敏页面/XHR 快照
  5. sync             : 去重后增量抓取（单次 1~3 场）并通过 /api/school-exams/*/sync-drafts
                        落库为未确认 ocr_draft 草稿，交由家长人工校对
  6. collect          : 采集 k12100 全科成绩/逐题明细/答题卡 JPEG 并导出 0600 脱敏 JSON 包（供管理端上传）
  7. backfill         : 一站式全科建档/总分确认/答题卡上传/已有原卷 PDF 提干与 ocr_draft 入库
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from getpass import getpass
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import ProxyHandler, Request, build_opener

REPO_ROOT = Path(__file__).resolve().parents[1]
_API_DIR = str(REPO_ROOT / "services" / "api")
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)

from shutong.k12100_backfill import (  # noqa: E402
    PII_AND_SECRET_KEYS,
    SUBJECT_ALIAS_MAP,
    clamp_max_exams,
    map_subject_code as _shared_map_subject_code,
    strip_pii_fields,
)

BROWSER_SCRIPT = REPO_ROOT / "scripts" / "k12100_browser.mjs"
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "shutong"
DEFAULT_API_URL = "http://127.0.0.1:18765"


def get_paths(config_dir: Path | None = None) -> dict[str, Path]:
    """统一解析宿主机私密配置路径（绝不落入仓库内部）。"""
    base = (config_dir or Path(os.getenv("SHUTONG_K12100_CONFIG_DIR") or DEFAULT_CONFIG_DIR)).expanduser()
    return {
        "dir": base,
        "env": base / "k12100.env",
        "profile": base / "k12100-browser-profile",
        "synced": base / "k12100-synced.json",
        "probe_dir": base / "probe_snapshot",
    }


def ensure_secure_dir(path: Path) -> None:
    """确保配置目录存在且权限收紧至 0700（仅当前用户可读/写/执行）。"""
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def validate_secure_permissions(path: Path, *, is_dir: bool = False) -> None:
    """严格拒绝权限过宽的文件或目录（存在任何同组/其他人权限位即报错拒载）。"""
    if not path.exists():
        raise FileNotFoundError(f"未找到私密配置：{path}，请先运行 init-credentials。")
    st = path.stat()
    mode = stat.S_IMODE(st.st_mode)
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        expected = "0700" if is_dir else "0600"
        raise PermissionError(
            f"安全检查失败：{path} 当前权限为 {oct(mode)}，暴露给了同组或其他用户！"
            f"请先执行 chmod {expected} '{path}' 收紧权限后重试。"
        )


def write_secure_file(path: Path, content: str) -> None:
    """以原子 0o600 权限覆盖写入机密或状态文件，防止短暂权限窗口泄漏。"""
    ensure_secure_dir(path.parent)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(tmp, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def load_env_credentials(env_path: Path) -> dict[str, str]:
    """校验目录与凭据文件权限后加载键值对。"""
    validate_secure_permissions(env_path.parent, is_dir=True)
    validate_secure_permissions(env_path, is_dir=False)
    creds: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        val = v.strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        creds[k.strip()] = val
    return creds


def mask_secret(value: str) -> str:
    """仅返回密钥首尾脱敏摘要，严禁向终端或日志输出明文。"""
    text = (value or "").strip()
    if not text:
        return "未配置"
    if len(text) <= 8:
        return "***"
    return f"{text[:4]}***{text[-4:]}"


def _format_env_lines(env_map: dict[str, str], *, comment_header: str) -> str:
    """按固定分组顺序渲染 .env 文件文本。"""
    preferred_order = [
        "PAGEBOY_HOME",
        "SHUTONG_ENV",
        "SHUTONG_STUDENT_TOKEN",
        "SHUTONG_ADMIN_TOKEN",
        "K12100_USERNAME",
        "K12100_PASSWORD",
        "K12100_PAGEBOY_API_URL",
        "DEEPSEEK_API_KEY",
        "SHUTONG_AI_API_KEY",
        "SHUTONG_VISION_API_KEY",
        "DEEPSEEK_BASE_URL",
        "SHUTONG_AI_BASE_URL",
        "SHUTONG_VISION_BASE_URL",
        "SHUTONG_AI_MODEL",
        "SHUTONG_TEXT_ENRICH_MODEL",
        "SHUTONG_VISION_MODEL",
    ]
    lines = [comment_header]
    seen: set[str] = set()
    for key in preferred_order:
        if key in env_map and env_map[key]:
            lines.append(f"{key}={env_map[key]}")
            seen.add(key)
    for key in sorted(env_map):
        if key not in seen and env_map[key]:
            lines.append(f"{key}={env_map[key]}")
    return "\n".join(lines) + "\n"


def merge_secure_env_file(
    env_path: Path,
    updates: dict[str, str],
    *,
    remove_keys: set[str] | None = None,
    comment_header: str = "# 书童 k12100.com 与 AI 本机私密凭据（禁止提交至 Git）",
) -> dict[str, str]:
    """在不破坏既有字段的前提下，原子 0600 合并写入私密配置文件。"""
    ensure_secure_dir(env_path.parent)
    existing: dict[str, str] = {}
    if env_path.exists():
        existing = load_env_credentials(env_path)
    for k in remove_keys or set():
        existing.pop(k, None)
    for k, v in updates.items():
        cleaned = str(v).strip()
        if cleaned:
            existing[k] = cleaned
    write_secure_file(env_path, _format_env_lines(existing, comment_header=comment_header))
    validate_secure_permissions(env_path.parent, is_dir=True)
    validate_secure_permissions(env_path, is_dir=False)
    return existing


def _build_deepseek_env_updates(
    api_key: str,
    *,
    base_url: str = "",
    vision_model: str = "",
    text_model: str = "",
) -> dict[str, str]:
    """构造 DeepSeek 与书童 AI 统一键值更新映射。"""
    cleaned_key = (api_key or "").strip()
    updates: dict[str, str] = {}
    if cleaned_key:
        updates["DEEPSEEK_API_KEY"] = cleaned_key
        updates["SHUTONG_AI_API_KEY"] = cleaned_key
        updates["SHUTONG_VISION_API_KEY"] = cleaned_key
    cleaned_url = (base_url or "").strip().rstrip("/")
    if cleaned_url:
        if not cleaned_url.startswith(("http://", "https://")):
            raise ValueError("DeepSeek Base URL 必须以 http:// 或 https:// 开头")
        updates["DEEPSEEK_BASE_URL"] = cleaned_url
        updates["SHUTONG_AI_BASE_URL"] = cleaned_url
        updates["SHUTONG_VISION_BASE_URL"] = cleaned_url
    if (vision_model or "").strip():
        updates["SHUTONG_VISION_MODEL"] = vision_model.strip()
    if (text_model or "").strip():
        updates["SHUTONG_AI_MODEL"] = text_model.strip()
        updates["SHUTONG_TEXT_ENRICH_MODEL"] = text_model.strip()
    return updates


_AI_SECRET_ENV_KEYS = {
    "DEEPSEEK_API_KEY",
    "SHUTONG_AI_API_KEY",
    "SHUTONG_VISION_API_KEY",
    "DEEPSEEK_BASE_URL",
    "SHUTONG_AI_BASE_URL",
    "SHUTONG_VISION_BASE_URL",
    "SHUTONG_AI_MODEL",
    "SHUTONG_TEXT_ENRICH_MODEL",
    "SHUTONG_VISION_MODEL",
}


def _resolve_dev_env_path(explicit_path: str = "") -> Path:
    """解析开发环境 dev.env 路径（遵循 PAGEBOY_HOME 约定）。"""
    if explicit_path:
        return Path(explicit_path).expanduser().resolve()
    pageboy_home = Path(os.getenv("PAGEBOY_HOME", "/media/xc/backup_ext4/pageboy-home")).expanduser().resolve()
    return pageboy_home / "development" / "env" / "dev.env"


def _sync_deepseek_to_dev_env(
    updates: dict[str, str],
    *,
    remove_keys: set[str] | None = None,
    dev_env_path: str = "",
) -> Path:
    """安全同步 AI 配置到 pageboy-home/development/env/dev.env（保留既有开发令牌）。"""
    target = _resolve_dev_env_path(dev_env_path)
    dev_home = target.parent.parent
    if not dev_home.is_dir():
        raise FileNotFoundError(f"开发环境 Home 目录不存在：{dev_home}，无法同步 dev.env")
    merge_secure_env_file(
        target,
        updates,
        remove_keys=remove_keys,
        comment_header="# 书童本地开发环境配置（仅开发态生效，严禁提交至 Git）",
    )
    return target


def map_subject_code(raw_subject: str) -> str:
    """将外部平台学科文本映射为书童支持的校考科目代码（兼容单科增量未知回退 math）。"""
    return _shared_map_subject_code(raw_subject, default="math") or "math"


def exam_fingerprint(exam: dict[str, Any]) -> str:
    """构造外部考试幂等去重指纹（优先平台 external_id，缺失则取科目+日期+标题哈希）。"""
    ext_id = str(exam.get("external_id") or "").strip()
    subj = map_subject_code(str(exam.get("subject_hint") or exam.get("subject") or "math"))
    if ext_id:
        return f"k12100:{subj}:{ext_id}"
    raw_key = f"{subj}|{exam.get('exam_date', '')}|{str(exam.get('title', '')).strip()}"
    return f"k12100:{subj}:sha:{sha256(raw_key.encode('utf-8')).hexdigest()[:16]}"


def load_synced_ledger(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"synced": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("synced"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"synced": {}}


def save_synced_ledger(path: Path, ledger: dict[str, Any]) -> None:
    write_secure_file(path, json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")


def _api_request(
    base_url: str,
    path: str,
    token: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    timeout: int = 240,
) -> Any:
    """访问本地或内网 Pageboy Admin API；回环地址绕过宿主代理避免 socks5 干扰。"""
    url = base_url.rstrip("/") + path
    is_loopback = (urlparse(url).hostname or "") in {"127.0.0.1", "localhost", "::1"}
    opener = build_opener(ProxyHandler({})) if is_loopback else build_opener()
    headers = {"Authorization": f"Bearer {token}"}
    data_bytes = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=data_bytes, headers=headers, method=method)
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Pageboy API {method} {path} 返回 HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"无法连接 Pageboy API ({url}): {exc.reason}") from exc


def sync_sanitized_exams_to_pageboy(
    raw_exams: list[dict[str, Any]],
    *,
    api_url: str,
    admin_token: str,
    ledger_path: Path,
    max_exams: int = 2,
    use_ai: bool = True,
    replace_unconfirmed_drafts: bool = False,
    force_resync: bool = False,
    dry_run: bool = False,
    request_fn=_api_request,
) -> dict[str, Any]:
    """将已脱敏的外部考试列表去重后同步为书童未确认 ocr_draft 草稿。"""
    capped = clamp_max_exams(max_exams)
    ledger = load_synced_ledger(ledger_path)
    synced_map: dict[str, Any] = ledger.setdefault("synced", {})
    existing_cache: dict[str, list[dict[str, Any]]] = {}

    summary = {"processed": 0, "skipped_dedup": 0, "drafts_created": 0, "exams": []}

    for raw_exam in raw_exams:
        if summary["processed"] >= capped:
            break
        clean_exam = strip_pii_fields(raw_exam)
        if not isinstance(clean_exam, dict):
            continue
        title = str(clean_exam.get("title") or "").strip()
        if not title:
            continue
        subject = map_subject_code(str(clean_exam.get("subject_hint") or clean_exam.get("subject") or "math"))
        exam_date = str(clean_exam.get("exam_date") or "")[:10]
        if len(exam_date) != 10:
            exam_date = "2026-10-15"
        fp = exam_fingerprint(clean_exam)

        if not force_resync and fp in synced_map:
            summary["skipped_dedup"] += 1
            summary["exams"].append({"title": title, "subject": subject, "status": "skipped_dedup"})
            continue

        earned_pts = float(clean_exam.get("earned_points") or 0.0)
        max_pts = float(clean_exam.get("max_points") or 100.0)
        if max_pts <= 0:
            max_pts = 100.0
        earned_pts = max(0.0, min(max_pts, earned_pts))

        items = []
        for idx, q in enumerate(clean_exam.get("items") or [], 1):
            if not isinstance(q, dict):
                continue
            q_max = float(q.get("max_points") or 2.0)
            if not (0 < q_max <= 100):
                q_max = 2.0
            q_earned = max(0.0, min(q_max, float(q.get("earned_points") or 0.0)))
            items.append(
                {
                    "question_label": str(q.get("question_label") or f"第{idx}题")[:160],
                    "earned_points": round(q_earned, 2),
                    "max_points": round(q_max, 2),
                    "stem_text": (str(q.get("stem_text") or "").strip()[:1800] or None),
                    "wrong_reason": (str(q.get("wrong_reason") or "").strip()[:480] or None),
                }
            )

        if dry_run:
            summary["processed"] += 1
            summary["exams"].append(
                {"title": title, "subject": subject, "exam_date": exam_date, "items_count": len(items), "status": "dry_run"}
            )
            continue

        if subject not in existing_cache:
            existing_cache[subject] = request_fn(api_url, f"/api/school-exams?{urlencode({'subject': subject})}", admin_token) or []
        matched = next((ex for ex in existing_cache[subject] if ex.get("title") == title and ex.get("exam_date") == exam_date), None)
        if matched:
            exam_id = str(matched["id"])
        else:
            created_exam = request_fn(
                api_url,
                "/api/school-exams",
                admin_token,
                method="POST",
                body={
                    "subject": subject,
                    "title": title[:200],
                    "exam_date": exam_date,
                    "earned_points": round(earned_pts, 2),
                    "max_points": round(max_pts, 2),
                    "confirmed_by_user": earned_pts > 0,
                },
            )
            exam_id = str(created_exam["id"])
            existing_cache[subject].append({"id": exam_id, "title": title, "exam_date": exam_date})

        created_count = 0
        if items:
            res = request_fn(
                api_url,
                f"/api/school-exams/{quote(exam_id, safe='')}/sync-drafts",
                admin_token,
                method="POST",
                body={
                    "source_name": "k12100",
                    "use_ai": use_ai,
                    "replace_unconfirmed_drafts": replace_unconfirmed_drafts,
                    "items": items,
                },
            )
            created_count = len((res or {}).get("created_items") or [])

        synced_map[fp] = {"exam_id": exam_id, "subject": subject, "title": title, "exam_date": exam_date, "items": created_count}
        save_synced_ledger(ledger_path, ledger)
        summary["processed"] += 1
        summary["drafts_created"] += created_count
        summary["exams"].append({"title": title, "subject": subject, "exam_id": exam_id, "created_drafts": created_count, "status": "synced"})

    return summary


def _resolve_deepseek_key(
    *,
    explicit_key: str = "",
    from_shell: bool = False,
    allow_prompt: bool = False,
    prompt_text: str = "请输入 DEEPSEEK_API_KEY（不回显）: ",
) -> tuple[str, str | None]:
    """解析 DeepSeek API Key，返回 (key, error_message)。"""
    cleaned = (explicit_key or "").strip()
    if cleaned:
        return cleaned, None
    if from_shell:
        shell_val = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if not shell_val:
            return "", "当前 Shell 环境变量 DEEPSEEK_API_KEY 未设置或为空。"
        return shell_val, None
    if allow_prompt:
        return getpass(prompt_text).strip(), None
    return "", None


def cmd_init_credentials(args: argparse.Namespace) -> int:
    """安全录入 k12100 凭据与可选 DeepSeek API Key，并合并写入 0600 文件。"""
    paths = get_paths(Path(args.config_dir) if args.config_dir else None)
    ensure_secure_dir(paths["dir"])

    existing: dict[str, str] = {}
    if paths["env"].exists():
        try:
            existing = load_env_credentials(paths["env"])
        except PermissionError as exc:
            print(f"错误：{exc}", file=sys.stderr)
            return 1

    updates: dict[str, str] = {}
    if not args.deepseek_only:
        non_interactive = bool(args.username and args.password)
        username = args.username.strip() if args.username else input("请输入 k12100.com 学生账号: ").strip()
        password = args.password.strip() if args.password else getpass("请输入 k12100.com 登录密码（不回显）: ").strip()
        if non_interactive:
            admin_token = args.admin_token.strip()
            raw_api_url = args.api_url.strip() or existing.get("K12100_PAGEBOY_API_URL") or DEFAULT_API_URL
        else:
            admin_token = (
                args.admin_token.strip()
                if args.admin_token
                else getpass("请输入书童管理端 Admin Token（SHUTONG_ADMIN_TOKEN，可留空）: ").strip()
            )
            default_url = existing.get("K12100_PAGEBOY_API_URL") or DEFAULT_API_URL
            raw_api_url = (
                args.api_url.strip()
                or input(f"书童 API 地址 [默认 {default_url}]: ").strip()
                or default_url
            )
        api_url = raw_api_url.rstrip("/")

        if not username or not password:
            print("错误：用户名和密码不能为空。", file=sys.stderr)
            return 1

        updates["K12100_USERNAME"] = username
        updates["K12100_PASSWORD"] = password
        updates["K12100_PAGEBOY_API_URL"] = api_url
        if admin_token:
            updates["SHUTONG_ADMIN_TOKEN"] = admin_token

    allow_deepseek_prompt = bool(
        (args.deepseek_only and not args.deepseek_api_key and not args.from_shell_deepseek)
        or (
            not args.deepseek_only
            and not (args.username and args.password)
            and sys.stdin.isatty()
            and not args.deepseek_api_key
            and not args.from_shell_deepseek
        )
    )
    deepseek_key, key_err = _resolve_deepseek_key(
        explicit_key=args.deepseek_api_key,
        from_shell=args.from_shell_deepseek,
        allow_prompt=allow_deepseek_prompt,
        prompt_text="请输入 DEEPSEEK_API_KEY（不回显，可留空跳过）: ",
    )
    if key_err:
        print(f"错误：{key_err}", file=sys.stderr)
        return 1

    try:
        ai_updates = _build_deepseek_env_updates(
            deepseek_key,
            base_url=args.deepseek_base_url,
            vision_model=args.deepseek_vision_model,
            text_model=args.deepseek_model,
        )
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    if args.deepseek_only and not ai_updates:
        print("错误：启用 --deepseek-only 时请至少提供 DEEPSEEK_API_KEY 或 Base URL / 模型配置。", file=sys.stderr)
        return 1
    updates.update(ai_updates)

    saved = merge_secure_env_file(paths["env"], updates)
    print(f"已安全写入凭据至 {paths['env']}（目录 0700，文件 0600，绝不进入仓库）。")
    if saved.get("K12100_USERNAME"):
        print(f"- k12100 账号：{saved['K12100_USERNAME'][:2]}***")
    if saved.get("DEEPSEEK_API_KEY"):
        print(f"- DEEPSEEK_API_KEY：{mask_secret(saved['DEEPSEEK_API_KEY'])}")

    if args.sync_dev_env and ai_updates:
        try:
            dev_target = _sync_deepseek_to_dev_env(ai_updates, dev_env_path=args.dev_env_path)
            print(f"- 已同步 AI 配置至开发环境：{dev_target}（0600）")
        except (FileNotFoundError, PermissionError, ValueError) as exc:
            print(f"错误：同步至 dev.env 失败：{exc}", file=sys.stderr)
            return 1
    return 0


def cmd_config_deepseek(args: argparse.Namespace) -> int:
    """单独配置、导入或清理 DeepSeek API Key 与模型参数，绝不覆盖 k12100 账号。"""
    paths = get_paths(Path(args.config_dir) if args.config_dir else None)
    ensure_secure_dir(paths["dir"])

    if args.clear:
        if paths["env"].exists():
            try:
                merge_secure_env_file(paths["env"], {}, remove_keys=_AI_SECRET_ENV_KEYS)
                print(f"已清理 {paths['env']} 中的 DeepSeek AI 配置（保留 k12100 凭据）。")
            except PermissionError as exc:
                print(f"错误：{exc}", file=sys.stderr)
                return 1
        else:
            print(f"私密凭据文件尚未创建（{paths['env']}），无需清理。")
        if args.sync_dev_env:
            try:
                dev_target = _sync_deepseek_to_dev_env({}, remove_keys=_AI_SECRET_ENV_KEYS, dev_env_path=args.dev_env_path)
                print(f"已清理开发环境中的 DeepSeek AI 配置：{dev_target}")
            except (FileNotFoundError, PermissionError, ValueError) as exc:
                print(f"错误：同步清理 dev.env 失败：{exc}", file=sys.stderr)
                return 1
        return 0

    has_other_opts = any([args.base_url, args.vision_model, args.text_model])
    deepseek_key, key_err = _resolve_deepseek_key(
        explicit_key=args.deepseek_api_key,
        from_shell=args.from_shell,
        allow_prompt=not args.deepseek_api_key and not args.from_shell and not has_other_opts,
        prompt_text="请输入 DEEPSEEK_API_KEY（不回显）: ",
    )
    if key_err:
        print(f"错误：{key_err}", file=sys.stderr)
        return 1

    try:
        ai_updates = _build_deepseek_env_updates(
            deepseek_key,
            base_url=args.base_url,
            vision_model=args.vision_model,
            text_model=args.text_model,
        )
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    if not ai_updates:
        print("错误：未提供 DEEPSEEK_API_KEY 或有效 AI 配置项。", file=sys.stderr)
        return 1

    try:
        saved = merge_secure_env_file(paths["env"], ai_updates)
    except PermissionError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    print(f"已安全写入 DeepSeek 配置至 {paths['env']}（目录 0700，文件 0600，绝不进入仓库）。")
    print(f"- DEEPSEEK_API_KEY：{mask_secret(saved.get('DEEPSEEK_API_KEY', ''))}")
    if saved.get("DEEPSEEK_BASE_URL"):
        print(f"- DEEPSEEK_BASE_URL：{saved['DEEPSEEK_BASE_URL']}")
    if saved.get("SHUTONG_VISION_MODEL"):
        print(f"- SHUTONG_VISION_MODEL：{saved['SHUTONG_VISION_MODEL']}")
    if saved.get("SHUTONG_AI_MODEL"):
        print(f"- SHUTONG_AI_MODEL：{saved['SHUTONG_AI_MODEL']}")

    if args.sync_dev_env:
        try:
            dev_target = _sync_deepseek_to_dev_env(ai_updates, dev_env_path=args.dev_env_path)
            print(f"- 已同步 AI 配置至开发环境：{dev_target}（0600）")
        except (FileNotFoundError, PermissionError, ValueError) as exc:
            print(f"错误：同步至 dev.env 失败：{exc}", file=sys.stderr)
            return 1
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """核对私密凭据权限、DeepSeek AI Key 状态与已同步场次统计（仅脱敏展示）。"""
    paths = get_paths(Path(args.config_dir) if args.config_dir else None)
    print(f"私密目录：{paths['dir']}")
    try:
        validate_secure_permissions(paths["dir"], is_dir=True)
        print("目录权限：0700 正常")
        creds = load_env_credentials(paths["env"])
        k12_user = creds.get("K12100_USERNAME", "")
        k12_pass = creds.get("K12100_PASSWORD", "")
        if k12_user and k12_pass:
            print(f"凭据状态：k12100 用户 {k12_user[:2]}***（0600 校验通过）")
        else:
            print("凭据状态：0600 校验通过（尚未配置 k12100 账号密码）")
    except (FileNotFoundError, PermissionError) as exc:
        print(f"凭据状态：{exc}", file=sys.stderr)
        return 1

    saved_ai_key = creds.get("DEEPSEEK_API_KEY") or creds.get("SHUTONG_VISION_API_KEY") or creds.get("SHUTONG_AI_API_KEY") or ""
    shell_ai_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if saved_ai_key:
        print(f"DeepSeek API Key：{mask_secret(saved_ai_key)}（已持久化至 0600 凭据文件）")
    elif shell_ai_key:
        print(f"DeepSeek API Key：{mask_secret(shell_ai_key)}（仅来自当前 Shell，可运行 config-deepseek --from-shell 持久化）")
    else:
        print("DeepSeek API Key：未配置")

    ledger = load_synced_ledger(paths["synced"])
    print(f"已去重归档考次：{len(ledger.get('synced') or {})} 场")
    print(f"浏览器 Profile：{paths['profile']} ({'已初始化' if paths['profile'].exists() else '首次探测/同步时自动创建'})")
    return 0


def _run_browser_node(mode: str, paths: dict[str, Path], creds: dict[str, str], args: argparse.Namespace) -> dict[str, Any]:
    ensure_secure_dir(paths["dir"])
    with TemporaryDirectory(prefix="shutong-k12100-") as td:
        out_path = Path(td) / "browser-out.json"
        cmd = [
            "node",
            str(BROWSER_SCRIPT),
            "--mode",
            mode,
            "--profile-dir",
            str(paths["profile"]),
            "--probe-dir",
            str(paths["probe_dir"]),
            "--output",
            str(out_path),
            "--max-exams",
            str(clamp_max_exams(getattr(args, "max_exams", 2))),
            "--wait-seconds",
            str(getattr(args, "wait_seconds", 180)),
        ]
        if mode == "probe" and hasattr(args, "probe_browse_seconds"):
            cmd.extend(["--probe-browse-seconds", str(args.probe_browse_seconds)])
        if getattr(args, "exam_keyword", ""):
            cmd.extend(["--exam-keyword", str(args.exam_keyword).strip()])
        if mode == "collect" and not getattr(args, "no_card_images", False):
            cmd.append("--fetch-card-images")
        if getattr(args, "headless", False):
            cmd.append("--headless")
        env = {
            **os.environ,
            "K12100_USERNAME": creds.get("K12100_USERNAME", ""),
            "K12100_PASSWORD": creds.get("K12100_PASSWORD", ""),
        }
        proc = subprocess.run(cmd, env=env, cwd=str(REPO_ROOT), check=False)
        if not out_path.exists():
            raise RuntimeError(f"浏览器脚本未产出结果文件（退出码 {proc.returncode}）")
        return json.loads(out_path.read_text(encoding="utf-8"))


def _require_k12100_credentials(creds: dict[str, str]) -> bool:
    """确认已配置 k12100 登录凭据，避免仅配置 DeepSeek 后直接启动浏览器报错。"""
    if creds.get("K12100_USERNAME") and creds.get("K12100_PASSWORD"):
        return True
    print("错误：尚未配置 k12100.com 账号或密码，请先执行 init-credentials。", file=sys.stderr)
    return False


def cmd_probe(args: argparse.Namespace) -> int:
    paths = get_paths(Path(args.config_dir) if args.config_dir else None)
    creds = load_env_credentials(paths["env"])
    if not _require_k12100_credentials(creds):
        return 1
    res = _run_browser_node("probe", paths, creds, args)
    print(json.dumps(strip_pii_fields(res), ensure_ascii=False, indent=2))
    return 0 if res.get("status") == "probed" else 2


def cmd_sync(args: argparse.Namespace) -> int:
    paths = get_paths(Path(args.config_dir) if args.config_dir else None)
    creds: dict[str, str] = {}
    if args.input_json:
        raw_payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
        raw_exams = raw_payload if isinstance(raw_payload, list) else (raw_payload.get("exams") or [])
        if paths["env"].exists():
            creds = load_env_credentials(paths["env"])
    else:
        creds = load_env_credentials(paths["env"])
        if not _require_k12100_credentials(creds):
            return 1
        browser_res = _run_browser_node("sync", paths, creds, args)
        if browser_res.get("status") != "synced_raw":
            print(json.dumps(strip_pii_fields(browser_res), ensure_ascii=False, indent=2), file=sys.stderr)
            return 2
        raw_exams = browser_res.get("exams") or []

    api_url = (args.api_url or creds.get("K12100_PAGEBOY_API_URL") or DEFAULT_API_URL).rstrip("/")
    admin_token = args.admin_token or os.getenv("SHUTONG_ADMIN_TOKEN") or creds.get("SHUTONG_ADMIN_TOKEN") or ""
    if not args.dry_run and not admin_token:
        print("错误：同步至书童 API 需要管理员令牌（--admin-token 或环境变量 SHUTONG_ADMIN_TOKEN）。", file=sys.stderr)
        return 1

    summary = sync_sanitized_exams_to_pageboy(
        raw_exams,
        api_url=api_url,
        admin_token=admin_token,
        ledger_path=paths["synced"],
        max_exams=args.max_exams,
        use_ai=not args.no_ai,
        replace_unconfirmed_drafts=args.replace_unconfirmed_drafts,
        force_resync=args.force_resync,
        dry_run=args.dry_run,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def backfill_sanitized_bundle_to_pageboy(
    raw_bundle: dict[str, Any],
    *,
    api_url: str,
    admin_token: str,
    ledger_path: Path,
    exam_keyword: str | None = None,
    target_exam_date: str | None = None,
    series_title_prefix: str | None = None,
    max_exams: int = 1,
    confirm_total_scores: bool = True,
    extract_existing_pdfs: bool = True,
    upload_missing_cards: bool = True,
    replace_unconfirmed_drafts: bool = True,
    use_ai: bool = True,
    dry_run: bool = False,
    request_fn=_api_request,
) -> dict[str, Any]:
    """将已脱敏 k12100 采集包通过统一 import-bundle 接口完成全科建档、提干与草稿入库。"""
    clean_bundle = strip_pii_fields(raw_bundle)
    if dry_run:
        exams = clean_bundle.get("exams") if isinstance(clean_bundle.get("exams"), list) else [clean_bundle]
        return {
            "dry_run": True,
            "exam_count": len(exams),
            "subjects": [
                {
                    "subjectName": s.get("subjectName") or s.get("subject"),
                    "score": s.get("score") or s.get("earned_points"),
                    "fullScore": s.get("fullScore") or s.get("max_points"),
                    "smallQuestionsCount": len(s.get("smallQuestions") or s.get("items") or []),
                }
                for pkt in exams[: clamp_max_exams(max_exams)]
                for s in (pkt.get("subjects") or [pkt])
                if isinstance(s, dict)
            ],
        }

    payload: dict[str, Any] = {
        "bundle": clean_bundle,
        "max_exams": clamp_max_exams(max_exams),
        "confirm_total_scores": bool(confirm_total_scores),
        "extract_existing_pdfs": bool(extract_existing_pdfs),
        "upload_missing_cards": bool(upload_missing_cards),
        "replace_unconfirmed_drafts": bool(replace_unconfirmed_drafts),
        "use_ai": bool(use_ai),
    }
    if exam_keyword:
        payload["exam_keyword"] = exam_keyword
    if target_exam_date:
        payload["target_exam_date"] = target_exam_date
    if series_title_prefix:
        payload["series_title_prefix"] = series_title_prefix

    res = request_fn(
        api_url,
        "/api/school-exams/k12100-sync/import-bundle",
        admin_token,
        method="POST",
        body=payload,
    )
    ledger = load_synced_ledger(ledger_path)
    synced_map: dict[str, Any] = ledger.setdefault("synced", {})
    for subj_res in res.get("subjects") or []:
        fp_key = f"{subj_res['subject']}|{subj_res['exam_date']}|{subj_res['exam_title']}"
        fp = f"k12100:{subj_res['subject']}:sha:{sha256(fp_key.encode('utf-8')).hexdigest()[:16]}"
        synced_map[fp] = {
            "title": subj_res["exam_title"],
            "subject": subj_res["subject"],
            "exam_date": subj_res["exam_date"],
            "source_exam_date": res.get("source_exam_date"),
            "school_exam_id": subj_res["exam_id"],
            "drafts_created": subj_res["drafts_created"],
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }
    save_synced_ledger(ledger_path, ledger)
    return res


def cmd_collect(args: argparse.Namespace) -> int:
    """采集全科成绩、逐题明细与答题卡 JPEG，以 0600 写入脱敏 JSON 采集包。"""
    paths = get_paths(Path(args.config_dir) if args.config_dir else None)
    try:
        creds = load_env_credentials(paths["env"])
    except (FileNotFoundError, PermissionError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    if not _require_k12100_credentials(creds):
        return 1

    raw_res = _run_browser_node("collect", paths, creds, args)
    if raw_res.get("status") != "collected":
        print(json.dumps(strip_pii_fields(raw_res), ensure_ascii=False, indent=2), file=sys.stderr)
        return 2 if raw_res.get("status") == "login_required" else 3

    clean_res = strip_pii_fields(raw_res)
    if args.output:
        out_path = Path(args.output).expanduser().resolve()
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = paths["probe_dir"] / f"k12100_bundle_{stamp}.json"
    write_secure_file(out_path, json.dumps(clean_res, ensure_ascii=False, indent=2) + "\n")

    summary = {
        "status": "collected",
        "output_file": str(out_path),
        "exams": [
            {
                "examName": ex.get("examName"),
                "examDate": ex.get("examDate"),
                "subjects": [
                    {
                        "subjectName": s.get("subjectName"),
                        "score": s.get("score"),
                        "fullScore": s.get("fullScore"),
                        "smallQuestions": len(s.get("smallQuestions") or []),
                        "cardImages": len(s.get("card_images") or []),
                    }
                    for s in (ex.get("subjects") or [])
                ],
            }
            for ex in (clean_res.get("exams") or [])
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def cmd_backfill(args: argparse.Namespace) -> int:
    """一站式全科补全：采集或加载离线采集包，调用 import-bundle 接口完成闭环。"""
    paths = get_paths(Path(args.config_dir) if args.config_dir else None)
    creds: dict[str, str] = {}
    if args.input_json:
        raw_bundle = json.loads(Path(args.input_json).expanduser().read_text(encoding="utf-8"))
        if paths["env"].exists():
            creds = load_env_credentials(paths["env"])
    else:
        try:
            creds = load_env_credentials(paths["env"])
        except (FileNotFoundError, PermissionError) as exc:
            print(f"错误：{exc}", file=sys.stderr)
            return 1
        if not _require_k12100_credentials(creds):
            return 1
        raw_bundle = _run_browser_node("collect", paths, creds, args)
        if raw_bundle.get("status") != "collected":
            print(json.dumps(strip_pii_fields(raw_bundle), ensure_ascii=False, indent=2), file=sys.stderr)
            return 2 if raw_bundle.get("status") == "login_required" else 3

    api_url = (args.api_url or creds.get("K12100_PAGEBOY_API_URL") or DEFAULT_API_URL).rstrip("/")
    admin_token = args.admin_token or os.getenv("SHUTONG_ADMIN_TOKEN") or creds.get("SHUTONG_ADMIN_TOKEN") or ""
    if not args.dry_run and not admin_token:
        print("错误：调用书童 API 需要管理员令牌（--admin-token 或环境变量 SHUTONG_ADMIN_TOKEN）。", file=sys.stderr)
        return 1

    summary = backfill_sanitized_bundle_to_pageboy(
        raw_bundle,
        api_url=api_url,
        admin_token=admin_token,
        ledger_path=paths["synced"],
        exam_keyword=args.exam_keyword or None,
        target_exam_date=args.target_exam_date or None,
        series_title_prefix=args.series_title_prefix or None,
        max_exams=args.max_exams,
        confirm_total_scores=args.confirm_total_scores,
        extract_existing_pdfs=not args.no_extract_pdfs,
        upload_missing_cards=not args.no_upload_cards,
        replace_unconfirmed_drafts=args.replace_unconfirmed_drafts,
        use_ai=not args.no_ai,
        dry_run=args.dry_run,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="书童 · k12100.com 拟人化安全同步与 DeepSeek 凭据配置 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-credentials", help="安全交互或 CLI 参数录入 k12100 账号及可选 DEEPSEEK_API_KEY（0600 合并保存）")
    p_init.add_argument("--config-dir", default="")
    p_init.add_argument("--username", default="")
    p_init.add_argument("--password", default="")
    p_init.add_argument("--admin-token", default="")
    p_init.add_argument("--api-url", default="")
    p_init.add_argument("--deepseek-api-key", default="", help="直接传入 DEEPSEEK_API_KEY 并同步设置 SHUTONG_AI_API_KEY / SHUTONG_VISION_API_KEY")
    p_init.add_argument("--from-shell-deepseek", action="store_true", help="从当前 Shell 环境变量 DEEPSEEK_API_KEY 读取并安全持久化")
    p_init.add_argument("--deepseek-base-url", default="", help="可选 DeepSeek API Base URL")
    p_init.add_argument("--deepseek-vision-model", default="", help="可选试卷视觉识别模型名")
    p_init.add_argument("--deepseek-model", default="", help="可选 DeepSeek 文本/助教模型名")
    p_init.add_argument("--deepseek-only", action="store_true", help="仅录入 DeepSeek 配置，跳过 k12100 账号密码")
    p_init.add_argument("--sync-dev-env", action="store_true", help="同步将 DeepSeek 配置安全写入 pageboy-home/development/env/dev.env（0600）")
    p_init.add_argument("--dev-env-path", default="", help="覆盖 dev.env 路径（主要用于测试）")
    p_init.set_defaults(func=cmd_init_credentials)

    p_ds = sub.add_parser("config-deepseek", help="单独配置、从 Shell 导入或清理 DEEPSEEK_API_KEY（保留既有 k12100 凭据）")
    p_ds.add_argument("--config-dir", default="")
    p_ds.add_argument("--deepseek-api-key", default="", help="传入 DEEPSEEK_API_KEY（不填则交互输入或配合 --from-shell 使用）")
    p_ds.add_argument("--from-shell", action="store_true", help="从当前 Shell 环境变量 DEEPSEEK_API_KEY 读取并安全持久化")
    p_ds.add_argument("--base-url", default="", help="可选 DeepSeek API Base URL")
    p_ds.add_argument("--vision-model", default="", help="可选视觉模型名")
    p_ds.add_argument("--text-model", default="", help="可选文本/助教模型名")
    p_ds.add_argument("--sync-dev-env", action="store_true", help="同时安全同步至 pageboy-home/development/env/dev.env（0600）")
    p_ds.add_argument("--dev-env-path", default="", help="覆盖 dev.env 路径（主要用于测试）")
    p_ds.add_argument("--clear", action="store_true", help="清除已保存的 DeepSeek AI 配置（保留 k12100 账号密码）")
    p_ds.set_defaults(func=cmd_config_deepseek)

    p_status = sub.add_parser("status", help="核对私密凭据权限、DeepSeek Key 状态与已去重场次统计")
    p_status.add_argument("--config-dir", default="")
    p_status.set_defaults(func=cmd_status)

    p_probe = sub.add_parser("probe", help="打开可见浏览器探测 k12100 登录后脱敏页面与 XHR 结构")
    p_probe.add_argument("--config-dir", default="")
    p_probe.add_argument("--wait-seconds", type=int, default=180)
    p_probe.add_argument("--probe-browse-seconds", type=int, default=20)
    p_probe.add_argument("--headless", action="store_true")
    p_probe.set_defaults(func=cmd_probe)

    p_sync = sub.add_parser("sync", help="执行去重限流同步，生成待人工核对 ocr_draft 草稿")
    p_sync.add_argument("--config-dir", default="")
    p_sync.add_argument("--api-url", default="")
    p_sync.add_argument("--admin-token", default="")
    p_sync.add_argument("--max-exams", type=int, default=2, help="单次最多抓取场次（硬限制 1~3）")
    p_sync.add_argument("--wait-seconds", type=int, default=180)
    p_sync.add_argument("--input-json", default="", help="直接从离线脱敏 JSON 演练/重放同步，不启动浏览器")
    p_sync.add_argument("--no-ai", action="store_true", help="跳过 DeepSeek 考点匹配，仅用本地关键词候选")
    p_sync.add_argument("--replace-unconfirmed-drafts", action="store_true")
    p_sync.add_argument("--force-resync", action="store_true")
    p_sync.add_argument("--dry-run", action="store_true")
    p_sync.add_argument("--headless", action="store_true")
    p_sync.set_defaults(func=cmd_sync)

    p_collect = sub.add_parser("collect", help="温和采集 k12100 全科快照并导出 0600 脱敏采集包 JSON")
    p_collect.add_argument("--config-dir", default="")
    p_collect.add_argument("--exam-keyword", default="", help="可选考试标题关键词，如 统一练习一")
    p_collect.add_argument("--max-exams", type=int, default=1, help="单次最多采集场次（硬限制 1~3）")
    p_collect.add_argument("--wait-seconds", type=int, default=180)
    p_collect.add_argument("--output", default="", help="可选输出 JSON 文件路径（默认写入 ~/.config/shutong/probe_snapshot/）")
    p_collect.add_argument("--no-card-images", action="store_true", help="跳过随包内嵌答题卡 JPEG 字节（仅保留安全链接）")
    p_collect.add_argument("--headless", action="store_true")
    p_collect.set_defaults(func=cmd_collect)

    p_backfill = sub.add_parser("backfill", help="一站式执行 k12100 全科对齐、答题卡上传、PDF 提干与 ocr_draft 入库")
    p_backfill.add_argument("--config-dir", default="")
    p_backfill.add_argument("--api-url", default="")
    p_backfill.add_argument("--admin-token", default="")
    p_backfill.add_argument("--input-json", default="", help="可选离线脱敏采集包 JSON，传入时直接导入不启浏览器")
    p_backfill.add_argument("--exam-keyword", default="")
    p_backfill.add_argument("--target-exam-date", default="", help="可选统一对齐日期 YYYY-MM-DD")
    p_backfill.add_argument("--series-title-prefix", default="", help="可选补建科目标题前缀")
    p_backfill.add_argument("--max-exams", type=int, default=1, help="单次最多同步场次（硬限制 1~3）")
    p_backfill.add_argument(
        "--confirm-total-scores",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="以 k12100 官方总分直接确认锁定未锁科目总分（默认开启）",
    )
    p_backfill.add_argument("--no-extract-pdfs", action="store_true", help="跳过从已有原卷 PDF 抽提真实题干")
    p_backfill.add_argument("--no-upload-cards", action="store_true", help="跳过为无附件科目补传答题卡 JPEG")
    p_backfill.add_argument(
        "--replace-unconfirmed-drafts",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="覆盖同题号尚未人工确认的旧 ocr_draft（默认开启）",
    )
    p_backfill.add_argument("--no-card-images", action="store_true")
    p_backfill.add_argument("--no-ai", action="store_true")
    p_backfill.add_argument("--headless", action="store_true")
    p_backfill.add_argument("--wait-seconds", type=int, default=180)
    p_backfill.add_argument("--dry-run", action="store_true")
    p_backfill.set_defaults(func=cmd_backfill)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
