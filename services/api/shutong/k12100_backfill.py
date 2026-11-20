"""k12100.com 全科校考信息补全编排引擎、SSRF 防护、原卷 PDF 提干与单任务运行管理。

严格守卫边界：
1. 不得导入或修改 `guidance.py`，`guidance.py` 保持纯领域计算与零 I/O。
2. 所有逐题草稿一律强制 `scoring_origin="ocr_draft"` 且 `confirmed_by_user=False`，
   必须经管理端「OCR / 同步草稿校对台」人工确认后方能进入能力画像与错误分析。
3. 任何外部答题卡图片 URL 均需通过 HTTPS、域名白名单、公网 IP 校验及体积/JPEG 魔数校验；
   所有采集载荷在入库、日志及响应前均执行递归 PII/凭据脱敏。
"""

from __future__ import annotations

import base64
from datetime import date, datetime, timezone
from hashlib import sha256
import inspect
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
from tempfile import TemporaryDirectory
import threading
from typing import Any, Callable
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import HTTPException
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from . import private_files as files
from . import school_paper_parser as paper_parser
from .home import (
    HomeIdentityError,
    assert_no_cross_environment_path,
    build_school_exam_archive_dir_name,
    get_env_home,
    normalize_environment,
    resolve_repo_root,
)
from .school_exam_matcher import ExamIdentity, match_exam_identity, normalize_academic_year
from .school_exam_pipeline import persist_rank_entries

# 单张答题卡 JPEG 与单次上传采集包 JSON 的体积安全上限
MAX_CARD_IMAGE_BYTES = 5 * 1024 * 1024
MAX_BUNDLE_BODY_BYTES = 15 * 1024 * 1024
ALLOWED_CARD_HOST_SUFFIXES = (".aliyuncs.com", ".k12100.com")
K12100_CONFIG_DIR_ENV = "SHUTONG_K12100_CONFIG_DIR"

SUBJECT_ALIAS_MAP: dict[str, str] = {
    "math": "math",
    "数学": "math",
    "chinese": "chinese",
    "语文": "chinese",
    "english": "english",
    "英语": "english",
    "physics": "physics",
    "物理": "physics",
    "ethics": "ethics",
    "道德与法治": "ethics",
    "道法": "ethics",
    "政治": "ethics",
    "思想品德": "ethics",
}

SUBJECT_CANONICAL_CN: dict[str, str] = {
    "chinese": "语文",
    "math": "数学",
    "english": "英语",
    "physics": "物理",
    "ethics": "道德与法治",
}

SUBJECT_TITLE_SUFFIX: dict[str, str] = {
    "chinese": "语文",
    "math": "数学",
    "english": "英语",
    "physics": "物理",
    "ethics": "道法",
}

# 含隐私或认证凭据字段（统一按小写比对；凡命中者一律清洗为占位符）
PII_AND_SECRET_KEYS: frozenset[str] = frozenset(
    {
        "student_name",
        "real_name",
        "user_name",
        "username",
        "nick_name",
        "xm",
        "student_id",
        "xuehao",
        "exam_no",
        "kaohao",
        "seat_no",
        "class_name",
        "school_name",
        "phone",
        "mobile",
        "tel",
        "id_card",
        "password",
        "pwd",
        "token",
        "access_token",
        "refresh_token",
        "cookie",
        "secret",
        "api_key",
        "shutong_admin_token",
        "authorization",
        "姓名",
        "学生姓名",
        "学号",
        "考号",
        "座位号",
        "班级",
        "学校",
        "手机号",
        "身份证",
        "studname",
        "studentname",
        "stuname",
        "classname",
        "schoolname",
        "studid",
        "studentid",
        "stucode",
        "studentno",
        "studentcode",
        "classidcode",
        "schoolid",
        "schoolrank",
        "classrank",
        "examrank",
        "regionrank",
        "examrankrate",
        "schoolrankrate",
        "groupclassranks",
        "examnum",
        "actualexamnum",
        "subjectleader",
        "createdby",
    }
)

_SERIES_SUFFIX_RE = re.compile(r"\s*[·・\-—]\s*(语文|数学|英语|物理|道德与法治|道法|政治)\s*$")
_HEADER_WATERMARK_RE = re.compile(r"(清华附|202\d\s*[~—-]\s*202\d|第\s*\d+\s*页.*共\s*\d+\s*页|扫描全能王|京考帮|学校.*统一练习)")

_JOB_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}
_JOB_ORDER: list[str] = []
_ACTIVE_JOB_ID: str | None = None
_MAX_RETAINED_JOBS = 10


def strip_pii_fields(value: Any, *, _depth: int = 0) -> Any:
    """递归移除所有已知隐私或敏感凭据字段（同时剔除键名与值），确保入库、响应与日志零泄漏。"""
    if _depth > 12:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for k, v in value.items():
            raw_k = str(k).strip()
            norm_k = raw_k.lower()
            if norm_k in PII_AND_SECRET_KEYS or raw_k in PII_AND_SECRET_KEYS:
                continue
            cleaned[str(k)] = strip_pii_fields(v, _depth=_depth + 1)
        return cleaned
    if isinstance(value, list):
        return [strip_pii_fields(item, _depth=_depth + 1) for item in value]
    return value


def sanitize_k12100_bundle_for_storage(raw_bundle: dict[str, Any]) -> dict[str, Any]:
    """导出/转交前清洗 PII，同时把已识别的本人排名白名单转为结构化字段保留。

    原始 schoolRank/classRank 等键名与值不会写入文件；只保留经过范围、来源字段、
    数值合法性校验后的 ``own_ranks`` 数组，供后续独立快照入库。
    """
    if not isinstance(raw_bundle, dict):
        return {}
    from .school_exam_pipeline import extract_own_rank_entries

    student_collection_keys = {"students", "studentlist", "examstudents", "classstudents", "ranklist"}

    def sanitize_packet(packet: dict[str, Any]) -> dict[str, Any]:
        clean_packet = strip_pii_fields(packet)
        for key in list(clean_packet):
            if str(key).lower() in student_collection_keys:
                clean_packet.pop(key, None)
        raw_subjects = packet.get("subjects")
        clean_subjects = clean_packet.get("subjects")
        if not isinstance(raw_subjects, list) or not isinstance(clean_subjects, list):
            return clean_packet
        sanitized_subjects: list[Any] = []
        for raw_subj, clean_subj in zip(raw_subjects, clean_subjects):
            if not isinstance(raw_subj, dict) or not isinstance(clean_subj, dict):
                sanitized_subjects.append(clean_subj)
                continue
            if isinstance(raw_subj.get("own_ranks"), list):
                own_ranks = raw_subj.get("own_ranks")
                rank_issues = raw_subj.get("rank_issues") if isinstance(raw_subj.get("rank_issues"), list) else []
            else:
                own_ranks, rank_issues = extract_own_rank_entries(raw_subj)
            rank_ownership = str(raw_subj.get("rank_ownership") or "unverified").strip().lower()
            if rank_ownership != "verified":
                if own_ranks:
                    rank_issues = [
                        *rank_issues,
                        {"scope": "rank", "code": "RANK_OWNERSHIP_UNVERIFIED"},
                    ]
                own_ranks = []
            structured_identity = extract_platform_exam_identity(packet, raw_subj)
            for key in list(clean_subj):
                if str(key).lower() in student_collection_keys:
                    clean_subj.pop(key, None)
            clean_subj["own_ranks"] = own_ranks
            clean_subj["rank_issues"] = rank_issues
            clean_subj["rank_ownership"] = rank_ownership
            clean_subj["rank_ownership_basis"] = str(
                raw_subj.get("rank_ownership_basis") or "structured_export_verified"
            )[:64]
            clean_subj["identity"] = structured_identity
            sanitized_subjects.append(clean_subj)
        clean_packet["subjects"] = sanitized_subjects
        return clean_packet

    if isinstance(raw_bundle.get("exams"), list):
        return {
            **{key: value for key, value in strip_pii_fields(raw_bundle).items() if key != "exams"},
            "exams": [sanitize_packet(item) for item in raw_bundle["exams"] if isinstance(item, dict)],
        }
    if isinstance(raw_bundle.get("subjects"), list):
        return sanitize_packet(raw_bundle)
    return strip_pii_fields(raw_bundle)


def mask_secret(raw: str | None) -> str | None:
    """将账号或 API Key 脱敏为首尾短前缀，绝不完整回显。"""
    text = (raw or "").strip()
    if not text:
        return None
    if len(text) <= 4:
        return f"{text[:1]}***"
    if len(text) <= 8:
        return f"{text[:2]}***{text[-1:]}"
    return f"{text[:4]}***{text[-4:]}"


def clamp_max_exams(value: int | None) -> int:
    """单次手动采集最多处理 1~3 场，防止异常翻页触发风控。"""
    if value is None:
        return 1
    return max(1, min(3, int(value)))


def map_subject_code(raw: str | None, *, default: str | None = None) -> str | None:
    """将中文或别名学科名称归一化为书童校考学科编码。"""
    if raw is None:
        return default
    text = str(raw).strip()
    if not text:
        return default
    if text.lower() in SUBJECT_ALIAS_MAP:
        return SUBJECT_ALIAS_MAP[text.lower()]
    for alias, code in SUBJECT_ALIAS_MAP.items():
        if alias in text:
            return code
    return default


def natural_question_sort_key(question_name_or_label: str) -> tuple[int, int, str]:
    """题号自然排序键：支持 `默写`（对齐语文第7题位置）及 `11（1）`/`第11题(1)` 小题。"""
    raw = str(question_name_or_label or "").strip()
    core = raw
    if core.startswith("第") and core.endswith("题"):
        core = core[1:-1].strip()
    elif core.startswith("第"):
        core = core[1:].strip()
        core = core.replace("题", "", 1).strip()
    if core == "默写" or raw == "默写":
        return (7, 0, raw)
    match = re.match(r"^(\d+)(?:[（\(](\d+)[）\)])?$", core)
    if match:
        return (int(match.group(1)), int(match.group(2) or 0), raw)
    num_match = re.search(r"(\d+)(?:[（\(](\d+)[）\)])?", raw)
    if num_match:
        return (int(num_match.group(1)), int(num_match.group(2) or 0), raw)
    return (999, 0, raw)


def resolve_k12100_config_dir(
    config_dir: Path | str | None = None,
    *,
    environment: str | None = None,
) -> Path:
    """解析当前环境的 k12100 凭据与浏览器配置目录，默认位于 $PAGEBOY_HOME/<env>/k12100。"""
    legacy_dir = (Path.home() / ".config" / "shutong").resolve()
    if config_dir is not None:
        resolved = Path(config_dir).expanduser().resolve()
    else:
        env_dir = os.getenv(K12100_CONFIG_DIR_ENV, "").strip()
        if env_dir:
            resolved = Path(env_dir).expanduser().resolve()
        else:
            resolved = (get_env_home(environment, require_identity=False) / "k12100").resolve()

    if resolved == legacy_dir or legacy_dir in resolved.parents:
        raise PermissionError("旧全局配置目录 ~/.config/shutong 已废弃，请改用 $PAGEBOY_HOME/<env>/k12100")
    return assert_no_cross_environment_path(resolved, expected_env=normalize_environment(environment))


def assert_private_path_mode(path: Path, expected_mode: int) -> None:
    """以 fail-closed 方式校验私密目录/文件权限，拒绝软链接及同组/他人访问权限。"""
    if path.is_symlink():
        raise PermissionError(f"安全策略拒绝读取符号链接：{path}")
    if os.name != "posix":
        return
    mode = stat.S_IMODE(path.lstat().st_mode)
    if (mode & 0o077) != 0 or mode != expected_mode:
        raise PermissionError(
            f"私密路径 {path} 权限必须为 {expected_mode:04o}（当前为 {mode:04o}），"
            f"请执行 chmod {expected_mode:03o} {path}"
        )


def parse_secure_env_file(env_path: Path) -> dict[str, str]:
    """解析 0600/0700 权限的 k12100.env，不满足权限即直接拒绝。"""
    if not env_path.exists():
        raise FileNotFoundError(f"未找到凭据文件：{env_path}")
    assert_private_path_mode(env_path.parent, 0o700)
    assert_private_path_mode(env_path, 0o600)
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        k, v = stripped.split("=", 1)
        values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def inspect_k12100_credentials(config_dir: Path | str | None = None) -> dict[str, Any]:
    """只读检查 k12100 凭据状态并返回脱敏摘要，绝不外泄密码或 API Key。"""
    try:
        cfg_dir = resolve_k12100_config_dir(config_dir)
    except (PermissionError, HomeIdentityError) as exc:
        return {
            "status": "permission_error",
            "username_masked": None,
            "deepseek_configured": False,
            "deepseek_masked": None,
            "message": str(exc),
        }
    env_path = cfg_dir / "k12100.env"
    if not env_path.exists():
        return {
            "status": "missing",
            "username_masked": None,
            "deepseek_configured": False,
            "deepseek_masked": None,
            "message": "宿主机尚未配置 k12100 账号（请先用 CLI 执行 init-credentials）。",
        }
    try:
        creds = parse_secure_env_file(env_path)
    except PermissionError as exc:
        return {
            "status": "permission_error",
            "username_masked": None,
            "deepseek_configured": False,
            "deepseek_masked": None,
            "message": str(exc),
        }
    username = (creds.get("K12100_USERNAME") or "").strip()
    password = (creds.get("K12100_PASSWORD") or "").strip()
    deepseek_key = (
        creds.get("SHUTONG_AI_API_KEY")
        or creds.get("SHUTONG_VISION_API_KEY")
        or creds.get("DEEPSEEK_API_KEY")
        or ""
    ).strip()
    if not username or not password:
        return {
            "status": "incomplete",
            "username_masked": mask_secret(username),
            "deepseek_configured": bool(deepseek_key),
            "deepseek_masked": mask_secret(deepseek_key),
            "message": "k12100.env 中缺少 K12100_USERNAME 或 K12100_PASSWORD。",
        }
    return {
        "status": "ready",
        "username_masked": mask_secret(username),
        "deepseek_configured": bool(deepseek_key),
        "deepseek_masked": mask_secret(deepseek_key),
        "message": "宿主机持久化配置与私密权限校验通过。",
    }


def _is_isolated_container() -> bool:
    """判断当前后端是否运行于禁用本机浏览器的隔离容器环境中。"""
    if os.getenv("SHUTONG_DISABLE_LOCAL_K12100_RUNNER", "").strip().lower() in {"1", "true", "yes"}:
        return True
    return Path("/.dockerenv").exists()


def _find_node_binary() -> str | None:
    """定位宿主机 Node.js 可执行文件，兼顾受限服务 PATH 场景。"""
    found = shutil.which("node")
    if found:
        return found
    for candidate in ("/usr/local/bin/node", "/usr/bin/node"):
        if Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def _is_host_allowed(host: str) -> bool:
    lowered = host.rstrip(".").lower()
    for suffix in ALLOWED_CARD_HOST_SUFFIXES:
        bare = suffix.lstrip(".")
        if lowered == bare or lowered.endswith(suffix):
            return True
    return False


def validate_safe_remote_card_url(url: str) -> str:
    """校验外部答题卡图片 URL：强制 HTTPS、白名单域名且解析 IP 必须为公网地址（防 SSRF）。"""
    cleaned = str(url or "").strip()
    parsed = urlparse(cleaned)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise HTTPException(422, detail="K12100_UNSAFE_CARD_URL")
    if parsed.username or parsed.password:
        raise HTTPException(422, detail="K12100_UNSAFE_CARD_URL")
    if parsed.port not in (None, 443):
        raise HTTPException(422, detail="K12100_UNSAFE_CARD_URL")
    host = parsed.hostname
    if not _is_host_allowed(host):
        raise HTTPException(422, detail="K12100_UNSAFE_CARD_URL")

    try:
        addr_infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise HTTPException(422, detail="K12100_UNSAFE_CARD_URL") from exc
    if not addr_infos:
        raise HTTPException(422, detail="K12100_UNSAFE_CARD_URL")

    for info in addr_infos:
        ip_str = info[4][0]
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError as exc:
            raise HTTPException(422, detail="K12100_UNSAFE_CARD_URL") from exc
        if (
            not ip_obj.is_global
            or ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_reserved
            or ip_obj.is_unspecified
        ):
            raise HTTPException(422, detail="K12100_UNSAFE_CARD_URL")
    return cleaned


def download_safe_card_image(url: str) -> bytes:
    """安全下载远程答题卡 JPEG：限制字节上限、严格验证重定向目标及 JPEG 文件头。"""
    current_url = validate_safe_remote_card_url(url)
    with httpx.Client(timeout=20.0, follow_redirects=False) as client:
        for _ in range(3):
            with client.stream("GET", current_url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                if resp.status_code in {301, 302, 303, 307, 308}:
                    location = resp.headers.get("location")
                    if not location:
                        raise HTTPException(422, detail="K12100_UNSAFE_CARD_URL")
                    current_url = validate_safe_remote_card_url(location)
                    continue
                if resp.status_code != 200:
                    raise HTTPException(502, detail="K12100_CARD_DOWNLOAD_FAILED")
                buf = bytearray()
                for chunk in resp.iter_bytes():
                    if len(buf) + len(chunk) > MAX_CARD_IMAGE_BYTES:
                        raise HTTPException(413, detail="INVALID_FILE_SIZE")
                    buf.extend(chunk)
                raw = bytes(buf)
                if not raw.startswith(b"\xff\xd8\xff"):
                    raise HTTPException(422, detail="UNSUPPORTED_FILE_TYPE")
                files.validate_file(raw, "image/jpeg")
                return raw
    raise HTTPException(422, detail="K12100_UNSAFE_CARD_URL")


def decode_embedded_card_image(entry: Any, *, default_filename: str) -> tuple[str, bytes]:
    """解析采集包内嵌的 Base64 答题卡 JPEG，执行魔数与体积上限校验。"""
    if isinstance(entry, dict):
        filename = str(entry.get("filename") or default_filename).strip() or default_filename
        raw_b64 = str(entry.get("data_base64") or entry.get("base64") or "").strip()
    elif isinstance(entry, str):
        filename = default_filename
        raw_b64 = entry.strip()
    else:
        raise HTTPException(422, detail="K12100_INVALID_BUNDLE")

    if raw_b64.startswith("data:"):
        _, _, raw_b64 = raw_b64.partition(",")
    # 先拦截明显超体积 Base64 字符串，避免解码爆内存
    if len(raw_b64) > MAX_CARD_IMAGE_BYTES * 2:
        raise HTTPException(413, detail="INVALID_FILE_SIZE")
    try:
        raw = base64.b64decode(raw_b64, validate=True)
    except Exception as exc:
        raise HTTPException(422, detail="K12100_INVALID_BUNDLE") from exc
    if len(raw) > MAX_CARD_IMAGE_BYTES:
        raise HTTPException(413, detail="INVALID_FILE_SIZE")
    if not raw.startswith(b"\xff\xd8\xff"):
        raise HTTPException(422, detail="UNSUPPORTED_FILE_TYPE")
    files.validate_file(raw, "image/jpeg")
    safe_name = os.path.basename(filename)[:200] or default_filename
    return safe_name, raw


def _strip_pdf_headers(text: str) -> str:
    """剔除学校试卷常见页眉页码与扫描水印，保留有效题干文本。"""
    lines: list[str] = []
    for raw_ln in text.splitlines():
        s = raw_ln.strip()
        if not s:
            continue
        if _HEADER_WATERMARK_RE.search(s):
            continue
        lines.append(s)
    return "\n".join(lines)


def _split_local_pdf_stems(text: str, expected_labels: list[str]) -> dict[str, str]:
    """按单调题号切分本地试卷文本，用于在无 DeepSeek Key 时生成基础题干摘要。"""
    cleaned = _strip_pdf_headers(text)
    if not cleaned:
        return {}
    blocks: dict[str, list[str]] = {}
    current_key: str | None = None
    expected_set = set(expected_labels)
    for ln in cleaned.splitlines():
        m = re.match(r"^\s*(?:第\s*)?(\d{1,2}(?:[（\(]\d+[）\)])?)\s*(?:[．.\、\)题])\s*(.*)$", ln)
        if m:
            candidate = paper_parser.normalize_question_label(m.group(1))
            if candidate in expected_set:
                current_key = candidate
                tail = m.group(2).strip()
                blocks[current_key] = [tail] if tail else []
                continue
        if current_key is not None:
            if re.match(r"^(?:第[一二三四五六]部分|[一二三四五六七八]、)", ln):
                continue
            blocks.setdefault(current_key, []).append(ln)

    stems: dict[str, str] = {}
    for lbl in expected_labels:
        joined = re.sub(r"\s+", " ", " ".join(blocks.get(lbl, []))).strip()
        if joined:
            stems[lbl] = joined[:320]
    return stems


def _pick_exam_paper_pdf(db: Session, *, exam_id: str, owner: str) -> m.SchoolPaperAttachment | None:
    """优先挑选考卷 PDF 原件（文件名含 卷/题 且非纯答题卡），若无则退回首个 PDF。"""
    atts = (
        db.execute(
            select(m.SchoolPaperAttachment)
            .where(
                m.SchoolPaperAttachment.school_exam_id == exam_id,
                m.SchoolPaperAttachment.owner_id == owner,
                m.SchoolPaperAttachment.media_type == "application/pdf",
            )
            .order_by(m.SchoolPaperAttachment.created_at, m.SchoolPaperAttachment.id)
        )
        .scalars()
        .all()
    )
    if not atts:
        return None

    def _priority(att: m.SchoolPaperAttachment) -> tuple[int, str]:
        name = att.filename or ""
        score = 0
        if "卷" in name or "题" in name:
            score += 2
        if "答" in name:
            score -= 2
        return (-score, att.id)

    atts.sort(key=_priority)
    return atts[0]


def extract_exam_pdf_stems(
    db: Session,
    *,
    exam: m.SchoolExam,
    owner: str,
    subject: str,
    expected_labels: list[str],
    use_ai: bool,
) -> tuple[dict[str, str], str]:
    """从库中已有原卷 PDF 提取题干：支持 DeepSeek 对齐提炼，无 Key 或异常时安全回退本地切分。"""
    att = _pick_exam_paper_pdf(db, exam_id=exam.id, owner=owner)
    if att is None:
        return {}, "no_pdf"
    try:
        blob = files.load_blob(att)
        raw_text, _ = files.parse_text(blob, att.media_type)
    except HTTPException:
        return {}, "pdf_parse_failed"
    cleaned = _strip_pdf_headers(raw_text)
    if not cleaned:
        return {}, "empty_pdf"

    cfg = paper_parser.load_vision_config(require_key=False) if use_ai else None
    if cfg is not None and expected_labels:
        subject_cn = SUBJECT_CANONICAL_CN.get(subject, subject)
        batch_size = 12 if len(expected_labels) > 16 else len(expected_labels)
        extracted: dict[str, str] = {}
        try:
            for start in range(0, len(expected_labels), batch_size):
                batch_labels = expected_labels[start : start + batch_size]
                prompt = (
                    f"下面是初中【{subject_cn}】试卷的本地提取/OCR 文本（已脱敏，不含个人隐私）。\n"
                    f"请严格按下面给定的标准题号列表（共 {len(batch_labels)} 题），逐一提取并归纳每道题的核心题干与设问"
                    "（修复明显 OCR 错字；语文“默写”可概括对应古诗文默写小题；带材料的题目简明概括材料主题与该小题设问，每题 180 字内；"
                    "仅保留试卷中存在的内容，严禁臆造）。\n"
                    '输出严格 JSON 对象：{"stems": [{"question_label": "原样保留", "stem_text": "..."}]}\n'
                    f"标准题号列表：{json.dumps(batch_labels, ensure_ascii=False)}\n\n"
                    f"试卷文本：\n{cleaned[:12000]}"
                )
                resp = paper_parser._post_deepseek_json(
                    cfg,
                    model=cfg.text_model,
                    messages=[
                        {"role": "system", "content": "你是初中教学试卷整理助手，只输出严格 JSON 对象，不做无根据臆测。"},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=4096,
                )
                for row in resp.get("stems") or []:
                    if not isinstance(row, dict):
                        continue
                    lbl = paper_parser.normalize_question_label(str(row.get("question_label") or ""))
                    txt = re.sub(r"\s+", " ", str(row.get("stem_text") or "")).strip()
                    if lbl and txt:
                        extracted[lbl] = txt[:320]
            if extracted:
                return extracted, "pdf_deepseek"
        except paper_parser.VisionParserUnavailableError:
            pass

    local_stems = _split_local_pdf_stems(cleaned, expected_labels)
    return local_stems, "pdf_local_regex"


def _english_section_label(raw_qname: str) -> str:
    """在缺少英语原卷 PDF 时，提供基于标准试卷结构的大题分节客观定位。"""
    if not raw_qname.isdigit():
        return "英语试题"
    q_num = int(raw_qname)
    if 1 <= q_num <= 20:
        return "第一部分 听后选择"
    if 21 <= q_num <= 32:
        return "第二部分 单项选择"
    if 33 <= q_num <= 40:
        return "第三部分 完形填空"
    if 41 <= q_num <= 53:
        return "第四部分 阅读理解"
    if 54 <= q_num <= 57:
        return "第五部分 阅读表达主观题"
    return "第六部分 书面表达/写作主观题"


def _parse_date_safe(raw: Any) -> date | None:
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    if isinstance(raw, datetime):
        return raw.date()
    text = str(raw or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def _extract_series_prefix(title: str | None) -> str:
    text = str(title or "").strip()
    return _SERIES_SUFFIX_RE.sub("", text).strip()


def _normalize_subject_entry(raw_subj: dict[str, Any], *, fallback_title: str, fallback_date: str | None) -> dict[str, Any] | None:
    """将多种上游科目录（原始抓取或已归一化条目）统一转换为内部结构。"""
    subject_code = map_subject_code(
        raw_subj.get("subject")
        or raw_subj.get("subjectName")
        or raw_subj.get("subject_hint")
    )
    if subject_code is None:
        return None

    small_raw = raw_subj.get("smallQuestions")
    if isinstance(small_raw, dict):
        small_raw = small_raw.get("tableData")
    if small_raw is None:
        small_raw = raw_subj.get("items") or []

    card_pages = raw_subj.get("cardPages") or raw_subj.get("pageVOS") or []
    earned = raw_subj.get("earned_points", raw_subj.get("score"))
    full = raw_subj.get("max_points", raw_subj.get("fullScore"))

    normalized_sqs: list[dict[str, Any]] = []
    for sq in small_raw:
        if not isinstance(sq, dict):
            continue
        qname = str(sq.get("questionName") or sq.get("question_label") or "").strip()
        if not qname:
            continue
        q_full = round(float(sq.get("fullScore") if sq.get("fullScore") is not None else sq.get("max_points") or 2.0), 2)
        if q_full <= 0:
            q_full = 2.0
        q_earned = round(float(sq.get("score") if sq.get("score") is not None else sq.get("earned_points") or 0.0), 2)
        q_earned = max(0.0, min(q_full, q_earned))
        normalized_sqs.append(
            {
                "raw_qname": qname,
                "question_label": paper_parser.normalize_question_label(qname),
                "earned_points": q_earned,
                "max_points": q_full,
                "question_type": str(sq.get("questionTypeName") or sq.get("question_type") or "题").strip(),
                "difficulty": str(sq.get("difficultyName") or sq.get("difficulty") or "-").strip(),
                "class_avg": sq.get("classAvgScore"),
                "grade_avg": sq.get("gradeAvgScore"),
                "stem_text": str(sq.get("stem_text") or "").strip(),
                "wrong_reason": str(sq.get("wrong_reason") or "").strip(),
            }
        )

    normalized_sqs.sort(key=lambda item: natural_question_sort_key(item["raw_qname"]))

    # 若顶层未给出科目满分/得分，从逐题分数稳健求和兜底
    inferred_full = round(sum(it["max_points"] for it in normalized_sqs), 2) or 100.0
    inferred_earned = round(sum(it["earned_points"] for it in normalized_sqs), 2)
    final_full = round(float(full), 2) if full is not None else inferred_full
    if final_full <= 0:
        final_full = inferred_full
    final_earned = round(float(earned), 2) if earned is not None else inferred_earned
    final_earned = max(0.0, min(final_full, final_earned))

    qvo_by_label: dict[str, dict[str, str]] = {}
    if isinstance(card_pages, list):
        for page in card_pages:
            if not isinstance(page, dict):
                continue
            for qvo in page.get("questionVOS") or []:
                if not isinstance(qvo, dict):
                    continue
                lbl = paper_parser.normalize_question_label(str(qvo.get("questionName") or ""))
                if lbl:
                    qvo_by_label[lbl] = {
                        "answer": str(qvo.get("answer") or "").strip(),
                        "questionAnswer": str(qvo.get("questionAnswer") or "").strip(),
                    }

    return {
        "subject": subject_code,
        "subject_cn": SUBJECT_CANONICAL_CN.get(subject_code, subject_code),
        "title": str(raw_subj.get("title") or fallback_title).strip(),
        "exam_date": str(raw_subj.get("exam_date") or fallback_date or "").strip() or None,
        "earned_points": final_earned,
        "max_points": final_full,
        "small_questions": normalized_sqs,
        "qvo_by_label": qvo_by_label,
        "img_urls": [str(u).strip() for u in (raw_subj.get("imgUrlList") or raw_subj.get("img_urls") or []) if str(u).strip()],
        "card_images": list(raw_subj.get("card_images") or raw_subj.get("cardImagesBase64") or []),
    }


_PLATFORM_EXAM_TYPE = {
    "月考": "monthly",
    "月度考试": "monthly",
    "月度检测": "monthly",
    "monthly": "monthly",
    "期中": "midterm",
    "期中考试": "midterm",
    "midterm": "midterm",
    "期末": "final",
    "期末考试": "final",
    "final": "final",
    "统一练习": "unified_practice",
    "统一训练": "unified_practice",
    "unified_practice": "unified_practice",
}
_PLATFORM_TERM = {
    "第一学期": "first",
    "上学期": "first",
    "秋季学期": "first",
    "first": "first",
    "第二学期": "second",
    "下学期": "second",
    "春季学期": "second",
    "second": "second",
}


def _first_scalar(source: dict[str, Any], names: tuple[str, ...]) -> str | None:
    for name in names:
        value = source.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def extract_platform_exam_identity(packet: dict[str, Any], subject: dict[str, Any]) -> dict[str, Any]:
    """从原始平台响应中仅取本人所在考试身份字段，随后再清洗其余载荷。"""
    school = _first_scalar(subject, ("schoolName", "school_name")) or _first_scalar(
        packet, ("schoolName", "school_name", "organizationName")
    )
    grade = _first_scalar(subject, ("gradeName", "grade")) or _first_scalar(packet, ("gradeName", "grade"))
    raw_type = _first_scalar(subject, ("examTypeName", "examType")) or _first_scalar(
        packet, ("examTypeName", "examType")
    )
    raw_term = _first_scalar(subject, ("termName", "term")) or _first_scalar(packet, ("termName", "term"))
    academic_year = _first_scalar(subject, ("academicYear", "academic_year")) or _first_scalar(
        packet, ("academicYear", "academic_year")
    )
    series = _first_scalar(subject, ("seriesTitle", "seriesName")) or _first_scalar(
        packet, ("seriesTitle", "seriesName")
    )
    external_id = _first_scalar(subject, ("examId", "platformExamId", "externalExamId")) or _first_scalar(
        packet, ("examId", "platformExamId", "externalExamId")
    )
    raw_type_label = str(raw_type or "").strip()
    exam_type = _PLATFORM_EXAM_TYPE.get(raw_type_label.lower()) or _PLATFORM_EXAM_TYPE.get(raw_type_label)
    if exam_type is None and raw_type_label:
        exam_type = "other"
    term = _PLATFORM_TERM.get(str(raw_term or "").strip().lower()) or _PLATFORM_TERM.get(str(raw_term or "").strip())
    raw_date = _first_scalar(subject, ("examDate", "exam_date")) or _first_scalar(
        packet, ("examDate", "exam_date")
    )
    return {
        "school_name": school[:160] if school else None,
        "grade": grade[:20] if grade else None,
        "exam_type": exam_type,
        "exam_type_label": raw_type_label[:40] if raw_type_label else None,
        "academic_year": normalize_academic_year(academic_year),
        "exam_date": raw_date[:10] if raw_date else None,
        "term": term,
        "series_title": series[:160] if series else None,
        "external_exam_id": external_id[:80] if external_id else None,
    }


def _normalize_structured_rank_entries(items: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """校验 CLI 已结构化导出的 own_ranks，防止跨类型/越界值进入独立排名快照。"""
    entries: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []
    for item in items[:8]:
        if not isinstance(item, dict):
            continue
        scope = str(item.get("scope") or "")
        if scope not in {"class", "grade", "school", "region"}:
            issues.append({"scope": scope or "unknown", "code": "RANK_SCOPE_INVALID"})
            continue
        try:
            rank_value = int(item.get("rank_value"))
        except (TypeError, ValueError):
            issues.append({"scope": scope, "code": "RANK_VALUE_INVALID"})
            continue
        if isinstance(item.get("rank_value"), bool) or rank_value <= 0:
            issues.append({"scope": scope, "code": "RANK_VALUE_INVALID"})
            continue
        count = item.get("participant_count")
        if count is not None:
            try:
                count = int(count)
            except (TypeError, ValueError):
                count = None
            if isinstance(item.get("participant_count"), bool) or (count is not None and count < rank_value):
                issues.append({"scope": scope, "code": "RANK_EXCEEDS_PARTICIPANT_COUNT"})
                continue
        percentile = item.get("percentile")
        if percentile is not None:
            try:
                percentile = float(percentile)
            except (TypeError, ValueError):
                percentile = None
            if percentile is not None and not 0 < percentile <= 1:
                percentile = None
        entries.append(
            {
                "scope": scope,
                "rank_value": rank_value,
                "participant_count": count,
                "percentile": percentile,
                "source_field": str(item.get("source_field") or "own_rank")[:64],
            }
        )
    return entries, issues


def normalize_k12100_bundle(
    raw_bundle: dict[str, Any],
    *,
    exam_keyword: str | None = None,
    max_exams: int | None = None,
) -> list[dict[str, Any]]:
    """清洗并归一化采集包；本人排名白名单在递归 PII 清洗前抽取并结构化保留。"""
    if not isinstance(raw_bundle, dict):
        raise HTTPException(422, detail="K12100_INVALID_BUNDLE")

    raw_packets: list[dict[str, Any]]
    if isinstance(raw_bundle.get("exams"), list):
        raw_packets = [p for p in raw_bundle["exams"] if isinstance(p, dict)]
    elif isinstance(raw_bundle.get("subjects"), list):
        raw_packets = [raw_bundle]
    elif raw_bundle.get("smallQuestions") is not None or raw_bundle.get("items") is not None:
        raw_packets = [
            {
                "examName": raw_bundle.get("title") or raw_bundle.get("examName"),
                "examDate": raw_bundle.get("exam_date") or raw_bundle.get("examDate"),
                "subjects": [raw_bundle],
            }
        ]
    else:
        raise HTTPException(422, detail="K12100_INVALID_BUNDLE")

    # 延迟导入避免模块初始化循环，同时复用同一份排名白名单实现。
    from .school_exam_pipeline import extract_own_rank_entries

    keyword = (exam_keyword or "").strip()
    packets_out: list[dict[str, Any]] = []
    for pkt in raw_packets:
        exam_title = str(
            pkt.get("examName")
            or pkt.get("exam_title")
            or pkt.get("title")
            or "k12100 校考成绩同步"
        ).strip()
        exam_date_str = str(pkt.get("examDate") or pkt.get("exam_date") or "").strip() or None
        if keyword and keyword not in exam_title:
            subj_titles = " ".join(str(s.get("title") or "") for s in (pkt.get("subjects") or []) if isinstance(s, dict))
            if keyword not in subj_titles:
                continue

        normalized_subjects: list[dict[str, Any]] = []
        seen_subjs: set[str] = set()
        for raw_subj in pkt.get("subjects") or []:
            if not isinstance(raw_subj, dict):
                continue
            # 排名在清洗前抽取；导出包可能已携带经过结构化的 own_ranks（CLI collect）。
            if isinstance(raw_subj.get("own_ranks"), list):
                own_ranks, pre_issues = _normalize_structured_rank_entries(raw_subj["own_ranks"])
                raw_issues = raw_subj.get("rank_issues") if isinstance(raw_subj.get("rank_issues"), list) else []
                rank_issues = [
                    {
                        "scope": str(issue.get("scope") or "unknown")[:20],
                        "code": str(issue.get("code") or "RANK_SOURCE_INVALID")[:64],
                    }
                    for issue in raw_issues[:20]
                    if isinstance(issue, dict)
                ] + pre_issues
            else:
                own_ranks, rank_issues = extract_own_rank_entries(raw_subj)
            rank_ownership = str(raw_subj.get("rank_ownership") or "unverified").strip().lower()
            if rank_ownership != "verified":
                if own_ranks:
                    rank_issues = [*rank_issues, {"scope": "rank", "code": "RANK_OWNERSHIP_UNVERIFIED"}]
                own_ranks = []
            clean_subj = strip_pii_fields(raw_subj)
            norm = _normalize_subject_entry(clean_subj, fallback_title=exam_title, fallback_date=exam_date_str)
            if norm is None or norm["subject"] in seen_subjs:
                continue
            norm["own_ranks"] = own_ranks
            norm["rank_issues"] = rank_issues
            norm["rank_ownership"] = rank_ownership
            norm["rank_ownership_basis"] = str(
                raw_subj.get("rank_ownership_basis") or "structured_export_verified"
            )[:64]
            identity = extract_platform_exam_identity(pkt, raw_subj)
            structured_identity = raw_subj.get("identity") if isinstance(raw_subj.get("identity"), dict) else {}
            identity_fields = {
                "school_name": "school_name",
                "grade": "grade",
                "exam_type": "exam_type",
                "exam_type_label": "exam_type_label",
                "academic_year": "academic_year",
                "exam_date": "exam_date",
                "term": "term",
                "series_title": "series_title",
                "external_exam_id": "external_exam_id",
            }
            for target, source in identity_fields.items():
                if identity.get(target):
                    continue
                value = structured_identity.get(source)
                if isinstance(value, (str, int)) and str(value).strip():
                    identity[target] = str(value).strip()
            norm["identity"] = identity
            seen_subjs.add(norm["subject"])
            normalized_subjects.append(norm)

        if normalized_subjects:
            packets_out.append(
                {
                    "exam_title": exam_title,
                    "exam_date": exam_date_str,
                    "subjects": normalized_subjects,
                }
            )

    if not packets_out:
        raise HTTPException(422, detail="K12100_INVALID_BUNDLE")

    if max_exams is not None:
        packets_out = packets_out[: clamp_max_exams(max_exams)]
    return packets_out


def _build_sync_items_for_subject(
    subj_pkt: dict[str, Any],
    *,
    stems_by_label: dict[str, str],
) -> list[dict[str, Any]]:
    """拼装送入 `enrich_external_items_with_deepseek` 的结构化逐题列表（仅保留客观题目元数据）。"""
    subject = subj_pkt["subject"]
    subject_cn = subj_pkt["subject_cn"]
    qvo_by_label = subj_pkt["qvo_by_label"]
    out_items: list[dict[str, Any]] = []

    for sq in subj_pkt["small_questions"]:
        lbl = sq["question_label"]
        earned = float(sq["earned_points"])
        max_pts = float(sq["max_points"])
        qvo = qvo_by_label.get(lbl) or {}
        my_ans = str(qvo.get("answer") or "").strip()
        std_ans = str(qvo.get("questionAnswer") or "").strip()

        existing_stem = sq.get("stem_text") or ""
        pdf_stem = stems_by_label.get(lbl, "").strip()
        if pdf_stem:
            base_stem = pdf_stem
        elif existing_stem:
            base_stem = existing_stem
        elif subject == "english":
            base_stem = f"{_english_section_label(sq['raw_qname'])} · {lbl}"
        else:
            base_stem = f"{subject_cn} {lbl}"

        meta_parts = [f"[{sq['question_type']} · 难度{sq['difficulty']} · 满分{max_pts:g}分]"]
        if std_ans:
            meta_parts.append(f"我的作答:{my_ans or '未作答'}/标准答案:{std_ans}")
        stem_full = f"{base_stem} | {' '.join(meta_parts)}"[:1800]

        wrong_reason = sq.get("wrong_reason") or None
        if earned < max_pts and not wrong_reason:
            if std_ans and my_ans != std_ans:
                wrong_reason = (
                    f"客观题失分（作答 {my_ans or '未填'} ≠ 标准答案 {std_ans}，"
                    f"实得 {earned:g}/{max_pts:g} 分，年级均分 {sq.get('grade_avg') or '-'}）"
                )[:480]
            else:
                wrong_reason = (
                    f"失分待复盘（实得 {earned:g}/{max_pts:g} 分，"
                    f"班均 {sq.get('class_avg') or '-'} / 年级均 {sq.get('grade_avg') or '-'}）"
                )[:480]
        elif earned >= max_pts:
            wrong_reason = None

        out_items.append(
            {
                "question_label": lbl,
                "earned_points": earned,
                "max_points": max_pts,
                "stem_text": stem_full,
                "wrong_reason": wrong_reason,
            }
        )
    return out_items


def _collect_card_blobs(subj_pkt: dict[str, Any]) -> list[tuple[str, bytes]]:
    """优先解码内嵌答题卡 JPEG，否则经 SSRF 校验后下载 OSS 图片。"""
    subject_cn = subj_pkt["subject_cn"]
    blobs: list[tuple[str, bytes]] = []
    if subj_pkt["card_images"]:
        for idx, entry in enumerate(subj_pkt["card_images"], 1):
            fname, raw = decode_embedded_card_image(entry, default_filename=f"{subject_cn}答_第{idx}页.jpg")
            blobs.append((fname, raw))
        return blobs

    for idx, url in enumerate(subj_pkt["img_urls"], 1):
        raw = download_safe_card_image(url)
        blobs.append((f"{subject_cn}答_第{idx}页.jpg", raw))
    return blobs


def _resolve_shared_archive_dir(
    db: Session,
    *,
    owner: str,
    archive_exam_id: str | None,
    exam_date: Any,
    title: str,
) -> str | None:
    if archive_exam_id:
        target = db.get(m.SchoolExam, archive_exam_id)
        if target is not None and target.learner_id == owner:
            if not target.archive_dir:
                target.archive_dir = build_school_exam_archive_dir_name(target.exam_date, target.title, target.id)
                db.flush()
            files.ensure_school_exam_archive_dirs(target.archive_dir)
            return target.archive_dir
    all_subject_exams = db.execute(
        select(m.SchoolExam)
        .where(m.SchoolExam.learner_id == owner, m.SchoolExam.subject == "all")
        .order_by(m.SchoolExam.created_at.desc())
    ).scalars().all()
    month = str(exam_date)[:7] if exam_date else ""
    clean_title = (title or "").strip()
    for item in all_subject_exams:
        if month and str(item.exam_date)[:7] != month:
            continue
        if clean_title and clean_title not in item.title and item.title not in clean_title:
            continue
        if not item.archive_dir:
            item.archive_dir = build_school_exam_archive_dir_name(item.exam_date, item.title, item.id)
            db.flush()
        files.ensure_school_exam_archive_dirs(item.archive_dir)
        return item.archive_dir
    return None


def _call_save_paper(
    save_paper_fn: Callable[..., dict[str, Any]],
    db: Session,
    exam_id: str,
    owner: str,
    filename: str,
    media_type: str,
    raw_bytes: bytes,
    digest: str,
    *,
    archive_dir: str | None,
) -> dict[str, Any]:
    sig = inspect.signature(save_paper_fn)
    if "category" in sig.parameters or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        return save_paper_fn(
            db,
            exam_id,
            owner,
            filename,
            media_type,
            raw_bytes,
            digest,
            category="answer_sheet",
            archive_dir_override=archive_dir,
        )
    return save_paper_fn(db, exam_id, owner, filename, media_type, raw_bytes, digest)


def apply_k12100_bundle(
    db: Session,
    *,
    owner: str,
    raw_bundle: dict[str, Any],
    resolve_knowledge_fn: Callable[[Session, str, set[str]], tuple[bool, list[dict], dict[str, str], dict[str, list[str]]]],
    persist_drafts_fn: Callable[..., tuple[list[m.SchoolExamItem], list[str]]],
    save_paper_fn: Callable[..., dict[str, Any]],
    exam_keyword: str | None = None,
    target_exam_date: date | None = None,
    series_title_prefix: str | None = None,
    max_exams: int | None = None,
    confirm_total_scores: bool = False,
    extract_existing_pdfs: bool = True,
    upload_missing_cards: bool = True,
    replace_unconfirmed_drafts: bool = True,
    use_ai: bool = True,
    archive_exam_id: str | None = None,
) -> dict[str, Any]:
    """执行严格身份匹配后的全科补全；未唯一匹配时不合并，仅返回待人工处理结果。"""
    packets = normalize_k12100_bundle(raw_bundle, exam_keyword=exam_keyword, max_exams=max_exams)

    all_subject_results: list[dict[str, Any]] = []
    created_exams_count = 0
    confirmed_now_count = 0
    locked_conflicts_count = 0
    attachments_uploaded_total = 0
    drafts_created_total = 0
    blocked_subjects_count = 0
    ranks_created_total = 0

    for pkt in packets:
        pkt_date = _parse_date_safe(pkt.get("exam_date"))
        # R2 红线：平台未提供可验证日期时绝不补 today()；只允许显式 target 或真实平台日期。
        canonical_date = target_exam_date or pkt_date
        pkt_archive_dir = _resolve_shared_archive_dir(
            db,
            owner=owner,
            archive_exam_id=archive_exam_id,
            exam_date=canonical_date,
            title=pkt["exam_title"],
        )

        for subj_pkt in pkt["subjects"]:
            subject = subj_pkt["subject"]
            suffix = SUBJECT_TITLE_SUFFIX.get(subject, subj_pkt["subject_cn"])
            identity_data = subj_pkt.get("identity") or {}
            canonical_prefix = (
                (series_title_prefix or "").strip()
                or str(identity_data.get("series_title") or "").strip()
                or _extract_series_prefix(pkt["exam_title"])
                or pkt["exam_title"]
            )
            subj_specific_title = subj_pkt.get("title") or ""
            if subj_specific_title and subj_specific_title != pkt["exam_title"]:
                desired_title = subj_specific_title
            else:
                desired_title = f"{canonical_prefix} · {suffix}"

            platform_date = str(canonical_date) if canonical_date is not None else identity_data.get("exam_date")
            header_identity = ExamIdentity(
                exam_id=None,
                subject=subject,
                title=pkt["exam_title"],
                exam_date=platform_date,
                school_name=identity_data.get("school_name"),
                grade=identity_data.get("grade"),
                exam_type=identity_data.get("exam_type"),
                exam_type_label=identity_data.get("exam_type_label"),
                academic_year=identity_data.get("academic_year"),
                term=identity_data.get("term"),
                series_title=canonical_prefix,
                external_exam_id=identity_data.get("external_exam_id"),
            )
            candidates = db.execute(
                select(m.SchoolExam).where(m.SchoolExam.learner_id == owner)
            ).scalars().all()
            candidate_identities = [
                ExamIdentity(
                    exam_id=item.id,
                    subject=item.subject,
                    title=item.title,
                    exam_date=str(item.exam_date),
                    school_name=item.school_name,
                    grade=item.grade,
                    exam_type=item.exam_type,
                    exam_type_label=item.exam_type_label,
                    academic_year=item.academic_year,
                    term=item.term,
                    series_title=item.series_title,
                    external_exam_id=item.external_exam_id,
                )
                for item in candidates
            ]
            match_result = match_exam_identity(header_identity, candidate_identities)

            real_score = round(float(subj_pkt["earned_points"]), 2)
            real_full = round(float(subj_pkt["max_points"]), 2)
            created_new = False
            exam = None

            if match_result.state == "EXACT_MATCH" and match_result.best_exam_id:
                exam = db.get(m.SchoolExam, match_result.best_exam_id)
                if exam is None or exam.learner_id != owner:
                    exam = None
                    match_result.state = "NEEDS_REVIEW"
                    match_result.best_exam_id = None
                    match_result.reasons.append("唯一匹配行在写入前消失或不属于当前 owner，已阻断")
                else:
                    for identity_field in (
                        "school_name",
                        "grade",
                        "exam_type",
                        "exam_type_label",
                        "academic_year",
                        "term",
                        "series_title",
                        "external_exam_id",
                    ):
                        if not getattr(exam, identity_field):
                            setattr(exam, identity_field, getattr(header_identity, identity_field))

            if match_result.state == "EXACT_MATCH" and exam is not None:
                pass
            elif match_result.state == "NOT_FOUND" and canonical_date is not None:
                exam = m.SchoolExam(
                    learner_id=owner,
                    subject=subject,
                    title=desired_title[:160],
                    exam_date=canonical_date,
                    earned_points=real_score,
                    max_points=real_full,
                    confirmed_by_user=bool(confirm_total_scores),
                    school_name=header_identity.school_name,
                    grade=header_identity.grade,
                    exam_type=header_identity.exam_type,
                    exam_type_label=header_identity.exam_type_label,
                    academic_year=header_identity.academic_year,
                    term=header_identity.term,
                    series_title=canonical_prefix[:160],
                    external_exam_id=header_identity.external_exam_id,
                    source_kind="k12100",
                    archive_dir=pkt_archive_dir,
                )
                db.add(exam)
                db.flush()
                if not pkt_archive_dir:
                    pkt_archive_dir = build_school_exam_archive_dir_name(
                        exam.exam_date, canonical_prefix or exam.title, exam.id
                    )
                    exam.archive_dir = pkt_archive_dir
                files.ensure_school_exam_archive_dirs(pkt_archive_dir)
                db.commit()
                db.refresh(exam)
                created_exams_count += 1
                created_new = True
            else:
                blocked_subjects_count += 1
                no_verified_date = match_result.state == "NOT_FOUND" and canonical_date is None
                blocked_warning = (
                    "平台未提供可验证的考试日期，已停止自动建档；不得以当前日期或月初日期伪造。"
                    if no_verified_date
                    else "考试身份未能唯一匹配，已停止该科入账并保留候选供人工确认。"
                )
                all_subject_results.append(
                    {
                        "subject": subject,
                        "subject_label": SUBJECT_CANONICAL_CN.get(subject, subject),
                        "exam_id": "",
                        "exam_title": "",
                        "exam_date": str(canonical_date) if canonical_date is not None else "",
                        "earned_points": real_score,
                        "max_points": real_full,
                        "confirmed_by_user": False,
                        "score_status": "match_blocked",
                        "stem_mode": "skipped",
                        "parser_mode_used": "none",
                        "attachments_uploaded": 0,
                        "drafts_created": 0,
                        "skipped_labels": [],
                        "warning": blocked_warning,
                        "match_state": "AWAITING_EXAM_DATE" if no_verified_date else match_result.state,
                        "match_confidence": match_result.confidence,
                        "match_reasons": match_result.reasons,
                        "match_candidates": [item.as_dict() for item in match_result.candidates],
                        "ranks_created": 0,
                        "rank_issues": subj_pkt.get("rank_issues") or [],
                        "rank_ownership": subj_pkt.get("rank_ownership") or "unverified",
                        "rank_ownership_basis": subj_pkt.get("rank_ownership_basis") or "structured_export_verified",
                    }
                )
                continue

            warning_msg: str | None = None
            if created_new:
                score_status = "created_confirmed" if confirm_total_scores else "created_unconfirmed"
                if confirm_total_scores:
                    confirmed_now_count += 1
            elif exam.confirmed_by_user:
                if abs(exam.earned_points - real_score) <= 1e-4:
                    score_status = "already_confirmed_match"
                else:
                    score_status = "locked_conflict"
                    locked_conflicts_count += 1
                    warning_msg = (
                        f"库中已人工锁定总分 {exam.earned_points:g}/{exam.max_points:g} 分，"
                        f"与 k12100 成绩 {real_score:g}/{real_full:g} 分不同；按锁分红线保留原值未覆写。"
                    )
            else:
                if abs(exam.max_points - real_full) > 1e-4 and real_score <= real_full:
                    exam.max_points = real_full
                exam.earned_points = min(real_score, exam.max_points)
                if confirm_total_scores:
                    exam.confirmed_by_user = True
                    confirmed_now_count += 1
                    score_status = "confirmed_now"
                else:
                    score_status = "updated_unconfirmed"
                db.commit()
                db.refresh(exam)

            # 本人排名独立快照；不受总分锁定/科目划线影响，也绝不进入能力证据。
            rank_created = persist_rank_entries(
                db,
                exam=exam,
                owner=owner,
                subject_scope=subject,
                entries=subj_pkt.get("own_ranks") or [],
                source_name="k12100",
                ownership_status=str(subj_pkt.get("rank_ownership") or "unverified"),
                ownership_basis=str(subj_pkt.get("rank_ownership_basis") or "structured_export_verified"),
            )
            ranks_created_total += len(rank_created)
            if rank_created:
                db.commit()

            # 若该科当前没有答题卡附件且开启补全开关，写入已校验的答题卡 JPEG（落于档案 answer-sheet/，带 SHA-256 去重）
            existing_atts = db.execute(
                select(m.SchoolPaperAttachment).where(
                    m.SchoolPaperAttachment.school_exam_id == exam.id,
                    m.SchoolPaperAttachment.owner_id == owner,
                )
            ).scalars().all()
            existing_hashes = {a.sha256 for a in existing_atts}
            uploaded_for_subj = 0
            if upload_missing_cards and len(existing_atts) == 0:
                if not pkt_archive_dir:
                    pkt_archive_dir = exam.archive_dir or build_school_exam_archive_dir_name(
                        exam.exam_date, canonical_prefix or exam.title, exam.id
                    )
                if not exam.archive_dir:
                    exam.archive_dir = pkt_archive_dir
                    db.commit()
                for fname, raw_bytes in _collect_card_blobs(subj_pkt):
                    digest = sha256(raw_bytes).hexdigest()
                    if digest in existing_hashes:
                        continue
                    _call_save_paper(
                        save_paper_fn,
                        db,
                        exam.id,
                        owner,
                        fname,
                        "image/jpeg",
                        raw_bytes,
                        digest,
                        archive_dir=pkt_archive_dir,
                    )
                    existing_hashes.add(digest)
                    uploaded_for_subj += 1
                    attachments_uploaded_total += 1

            # 从库中原卷 PDF 抽取题干文本（无 PDF 时退回大题结构或平台原始描述）
            expected_labels = [sq["question_label"] for sq in subj_pkt["small_questions"]]
            if extract_existing_pdfs:
                stems_by_label, stem_mode = extract_exam_pdf_stems(
                    db,
                    exam=exam,
                    owner=owner,
                    subject=subject,
                    expected_labels=expected_labels,
                    use_ai=use_ai,
                )
            else:
                stems_by_label, stem_mode = {}, "disabled"

            external_items = _build_sync_items_for_subject(subj_pkt, stems_by_label=stems_by_label)
            if len(external_items) > 100:
                external_items = external_items[:100]

            if external_items:
                _, knowledge_catalog, _, _ = resolve_knowledge_fn(db, subject, set())
                enriched_items, enrich_mode = paper_parser.enrich_external_items_with_deepseek(
                    subject=subject,
                    knowledge_catalog=knowledge_catalog,
                    external_items=external_items,
                    use_ai=use_ai,
                )
                # 再次强制红线字段，确保即使调用方传入特殊映射也绝不绕过未确认草稿门禁
                for item in enriched_items:
                    item["scoring_origin"] = "ocr_draft"
                    item["confirmed_by_user"] = False
                created, skipped_labels = persist_drafts_fn(
                    db,
                    exam,
                    enriched_items,
                    replace_matching_unconfirmed=replace_unconfirmed_drafts,
                )
            else:
                enrich_mode = "none"
                created, skipped_labels = [], []

            drafts_created_total += len(created)
            all_subject_results.append(
                {
                    "subject": subject,
                    "subject_label": SUBJECT_CANONICAL_CN.get(subject, subject),
                    "exam_id": exam.id,
                    "exam_title": exam.title,
                    "exam_date": str(exam.exam_date),
                    "earned_points": exam.earned_points,
                    "max_points": exam.max_points,
                    "confirmed_by_user": exam.confirmed_by_user,
                    "score_status": score_status,
                    "stem_mode": stem_mode,
                    "parser_mode_used": enrich_mode,
                    "attachments_uploaded": uploaded_for_subj,
                    "drafts_created": len(created),
                    "skipped_labels": skipped_labels,
                    "warning": warning_msg,
                    "match_state": match_result.state,
                    "match_confidence": match_result.confidence,
                    "match_reasons": match_result.reasons,
                    "match_candidates": [item.as_dict() for item in match_result.candidates],
                    "ranks_created": len(rank_created),
                    "rank_issues": subj_pkt.get("rank_issues") or [],
                    "rank_ownership": subj_pkt.get("rank_ownership") or "unverified",
                    "rank_ownership_basis": subj_pkt.get("rank_ownership_basis") or "structured_export_verified",
                }
            )

    return {
        "source_exam_title": packets[0]["exam_title"],
        "source_exam_date": packets[0]["exam_date"],
        "subjects": all_subject_results,
        "totals": {
            "subjects_processed": len(all_subject_results),
            "subjects_blocked": blocked_subjects_count,
            "created_exams": created_exams_count,
            "confirmed_now": confirmed_now_count,
            "locked_conflicts": locked_conflicts_count,
            "attachments_uploaded": attachments_uploaded_total,
            "drafts_created": drafts_created_total,
            "ranks_created": ranks_created_total,
        },
        "knowledge_evidence_created": 0,
    }


def validate_collected_bundle(bundle: Any) -> dict[str, Any]:
    """把浏览器“空采集/无科目/未登录”等结果转成可操作错误，不用 INVALID_BUNDLE 混淆。"""
    if not isinstance(bundle, dict):
        raise RuntimeError("K12100_INVALID_BUNDLE: 浏览器返回的采集结果不是 JSON 对象")
    status = str(bundle.get("status") or "").strip()
    if status in {"login_incomplete", "login_required"}:
        raise RuntimeError("K12100_LOGIN_REQUIRED: 会话已失效或自动登录未完成，请勾选可见窗口重新登录后再试。")
    if status == "circuit_breaker":
        raise RuntimeError("K12100_CIRCUIT_BREAKER: 检测到验证码或频控（401/403/429），已立即熔断并停止采集。")
    exams = bundle.get("exams")
    if not isinstance(exams, list) or not exams:
        raise RuntimeError(
            "K12100_NO_EXAMS: 平台未列出可采集考试（可能关键词不匹配、页面无考试或账号无可见成绩）；未写入任何数据。"
        )
    has_subject = any(
        isinstance(subject, dict)
        for exam in exams
        if isinstance(exam, dict)
        for subject in (exam.get("subjects") or [])
    )
    if not has_subject:
        raise RuntimeError("K12100_NO_SUBJECTS: 已找到考试但未取得任何科目数据；未写入任何数据。")
    return bundle


def _collect_with_browser(
    *,
    config_dir: Path,
    creds: dict[str, str],
    exam_keyword: str | None,
    max_exams: int,
    fetch_card_images: bool,
    headless: bool,
) -> dict[str, Any]:
    """调用宿主机持久化 Playwright 脚本采集脱敏多科数据包，凭据仅通过子进程 env 注入。"""
    node_bin = _find_node_binary()
    if not node_bin:
        raise RuntimeError("K12100_LOCAL_RUNNER_UNAVAILABLE: 未找到宿主 Node.js")
    repo_root = resolve_repo_root(__file__)
    script_path = repo_root / "scripts" / "k12100_browser.mjs"
    if not script_path.is_file():
        raise RuntimeError("K12100_LOCAL_RUNNER_UNAVAILABLE: 缺少 scripts/k12100_browser.mjs")

    with TemporaryDirectory(prefix="shutong-k12100-") as tmpdir:
        out_path = Path(tmpdir) / "collected_bundle.json"
        cmd = [
            node_bin,
            str(script_path),
            "--mode",
            "collect",
            "--profile-dir",
            str(config_dir / "k12100-browser-profile"),
            "--output",
            str(out_path),
            "--max-exams",
            str(clamp_max_exams(max_exams)),
        ]
        if exam_keyword:
            cmd.extend(["--exam-keyword", exam_keyword.strip()])
        if fetch_card_images:
            cmd.append("--fetch-card-images")
        cmd.append("--headless" if headless else "--headed")

        child_env = os.environ.copy()
        child_env["K12100_USERNAME"] = creds["K12100_USERNAME"]
        child_env["K12100_PASSWORD"] = creds["K12100_PASSWORD"]

        res = subprocess.run(
            cmd,
            cwd=str(repo_root),
            env=child_env,
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
        if res.returncode == 2:
            raise RuntimeError("K12100_LOGIN_REQUIRED: 会话已失效或自动登录未完成，请勾选可见窗口重新登录后再试。")
        if res.returncode == 3:
            raise RuntimeError("K12100_CIRCUIT_BREAKER: 检测到验证码或频控（401/403/429），已立即熔断并停止采集。")
        if res.returncode != 0 or not out_path.is_file():
            raise RuntimeError("K12100_BROWSER_FAILED: 浏览器采集未能产出有效数据包，请检查网络或改用手动 CLI 导出包。")
        # 原始载荷仅在本进程内存中交给 apply 的排名白名单适配层，绝不持久化；
        # apply/normalize 会在抽取本人排名后再执行递归 PII 清洗。
        return validate_collected_bundle(json.loads(out_path.read_text(encoding="utf-8")))


def _snapshot_job(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": job["job_id"],
        "kind": job.get("kind", "legacy_collect"),
        "state": job["state"],
        "stage_message": job["stage_message"],
        "progress_percent": int(job.get("progress_percent") or 0),
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "exam_keyword": job.get("exam_keyword"),
        "confirm_total_scores": job.get("confirm_total_scores", True),
        "error_code": job.get("error_code"),
        "error_message": job.get("error_message"),
        "result": job.get("result"),
        "report_result": job.get("report_result"),
    }


def _update_job(job_id: str, **updates: Any) -> None:
    with _JOB_LOCK:
        job = _JOBS.get(job_id)
        if job is not None:
            job.update(updates)
            job["updated_at"] = datetime.now(timezone.utc).isoformat()


def launch_k12100_job(
    db: Session,
    *,
    kind: str,
    initial_stage_message: str,
    extra_fields: dict[str, Any] | None,
    worker_fn: Callable[[str, Path, dict[str, str], sessionmaker[Session]], None],
) -> dict[str, Any]:
    """宿主机环境下加锁启动单实例后台 k12100 任务（与旧任务互斥，禁止并发）。"""
    global _ACTIVE_JOB_ID

    cfg_dir = resolve_k12100_config_dir()
    runtime = get_k12100_runtime_status(cfg_dir)
    if not runtime["can_run_local"]:
        detail_code = runtime["unavailable_code"] or "K12100_LOCAL_RUNNER_UNAVAILABLE"
        raise HTTPException(409, detail=detail_code)

    creds = parse_secure_env_file(cfg_dir / "k12100.env")
    engine = db.get_bind()
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with _JOB_LOCK:
        if _ACTIVE_JOB_ID is not None:
            active_job = _JOBS.get(_ACTIVE_JOB_ID)
            if active_job and active_job["state"] in {"queued", "collecting", "backfilling"}:
                raise HTTPException(409, detail="K12100_SYNC_ALREADY_RUNNING")

        job_id = str(uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()
        job_record: dict[str, Any] = {
            "job_id": job_id,
            "kind": kind,
            "state": "queued",
            "stage_message": initial_stage_message,
            "progress_percent": 5,
            "created_at": now_iso,
            "updated_at": now_iso,
            "exam_keyword": None,
            "confirm_total_scores": False,
            "error_code": None,
            "error_message": None,
            "result": None,
            "report_result": None,
            **(extra_fields or {}),
        }
        _JOBS[job_id] = job_record
        _JOB_ORDER.append(job_id)
        while len(_JOB_ORDER) > _MAX_RETAINED_JOBS:
            evict_id = _JOB_ORDER.pop(0)
            _JOBS.pop(evict_id, None)
        _ACTIVE_JOB_ID = job_id
        initial_snapshot = _snapshot_job(job_record)

    def _run() -> None:
        global _ACTIVE_JOB_ID
        try:
            worker_fn(job_id, cfg_dir, creds, session_factory)
        except Exception as exc:
            if isinstance(exc, HTTPException):
                err_code = str(exc.detail or "K12100_SYNC_FAILED")
                err_msg = f"同步中止：{err_code}"
            else:
                raw_msg = str(exc)
                err_code, _, rest = raw_msg.partition(":")
                if err_code.startswith("K12100_") and rest:
                    err_msg = rest.strip()
                else:
                    err_code = "K12100_SYNC_FAILED"
                    err_msg = raw_msg[:240] or "后台同步执行失败。"
            _update_job(
                job_id,
                state="failed",
                stage_message=err_msg,
                error_code=err_code,
                error_message=err_msg,
            )
        finally:
            with _JOB_LOCK:
                if _ACTIVE_JOB_ID == job_id:
                    _ACTIVE_JOB_ID = None

    threading.Thread(target=_run, name=f"k12100-{kind}-{job_id[:8]}", daemon=True).start()
    return initial_snapshot


def get_k12100_runtime_status(config_dir: Path | str | None = None) -> dict[str, Any]:
    """探测当前后端运行态的 k12100 直连能力、脱敏凭据状态与任务进度。"""
    repo_root = resolve_repo_root(__file__)
    is_isolated = _is_isolated_container()
    node_bin = None if is_isolated else _find_node_binary()
    browser_script = repo_root / "scripts" / "k12100_browser.mjs"
    pw_pkg = repo_root / "apps" / "web" / "node_modules" / "playwright-core"
    browser_ready = bool((not is_isolated) and node_bin and browser_script.is_file() and pw_pkg.is_dir())

    cred_summary = inspect_k12100_credentials(config_dir)
    if is_isolated:
        unavailable_code: str | None = "K12100_LOCAL_RUNNER_UNAVAILABLE"
        unavailable_reason = "当前后端运行在安全隔离容器内（无浏览器且隔离机构凭据），请上传宿主机导出的脱敏采集包或使用 CLI 直连补全。"
    elif not browser_ready:
        unavailable_code = "K12100_LOCAL_RUNNER_UNAVAILABLE"
        unavailable_reason = "未检测到可用的宿主 Node.js 或 playwright-core 运行时，请上传宿主机脱敏采集包。"
    elif cred_summary["status"] != "ready":
        unavailable_code = "K12100_CREDENTIALS_NOT_CONFIGURED"
        unavailable_reason = cred_summary["message"]
    else:
        unavailable_code = None
        unavailable_reason = None

    with _JOB_LOCK:
        active_id = _ACTIVE_JOB_ID
        latest_job = _snapshot_job(_JOBS[_JOB_ORDER[-1]]) if _JOB_ORDER else None

    env_name = normalize_environment()
    env_deepseek = paper_parser.load_vision_config(require_key=False) is not None
    return {
        "environment": env_name,
        "mode": "host_direct" if unavailable_code is None else "isolated_import_only",
        "can_run_local": unavailable_code is None,
        "is_isolated": is_isolated,
        "browser_ready": browser_ready,
        "node_available": bool(node_bin),
        "playwright_available": pw_pkg.is_dir(),
        "unavailable_code": unavailable_code,
        "unavailable_reason": unavailable_reason,
        "credentials": cred_summary,
        "deepseek_configured": bool(env_deepseek or cred_summary["deepseek_configured"]),
        "active_job_id": active_id,
        "latest_job": latest_job,
        "recommended_cli_command": f"uv run python scripts/k12100_sync.py collect --env {env_name}",
    }


def get_k12100_sync_job(job_id: str) -> dict[str, Any] | None:
    """读取单次任务脱敏快照。"""
    with _JOB_LOCK:
        job = _JOBS.get(job_id)
        return _snapshot_job(job) if job is not None else None


def start_k12100_sync_job(
    db: Session,
    *,
    owner: str,
    resolve_knowledge_fn: Callable[[Session, str, set[str]], tuple[bool, list[dict], dict[str, str], dict[str, list[str]]]],
    persist_drafts_fn: Callable[..., tuple[list[m.SchoolExamItem], list[str]]],
    save_paper_fn: Callable[..., dict[str, Any]],
    exam_keyword: str | None = None,
    target_exam_date: date | None = None,
    series_title_prefix: str | None = None,
    max_exams: int = 1,
    confirm_total_scores: bool = True,
    extract_existing_pdfs: bool = True,
    upload_missing_cards: bool = True,
    replace_unconfirmed_drafts: bool = True,
    use_ai: bool = True,
    headless: bool = True,
    archive_exam_id: str | None = None,
) -> dict[str, Any]:
    """宿主机环境下加锁启动单实例后台 k12100 全科采集与补全任务（禁止并发）。"""

    def _worker(job_id: str, cfg_dir: Path, creds: dict[str, str], session_factory: sessionmaker[Session]) -> None:
        _update_job(
            job_id,
            state="collecting",
            stage_message="正在拟人化复用持久化会话抓取 k12100 各科成绩、明细与答题卡…",
        )
        collected = _collect_with_browser(
            config_dir=cfg_dir,
            creds=creds,
            exam_keyword=exam_keyword,
            max_exams=clamp_max_exams(max_exams),
            fetch_card_images=upload_missing_cards,
            headless=headless,
        )
        _update_job(
            job_id,
            state="backfilling",
            stage_message="已取得脱敏全科快照，正在对齐校考场次、抽取原卷题干并生成 ocr_draft 草稿…",
        )
        with session_factory() as worker_db:
            result = apply_k12100_bundle(
                worker_db,
                owner=owner,
                raw_bundle=collected,
                resolve_knowledge_fn=resolve_knowledge_fn,
                persist_drafts_fn=persist_drafts_fn,
                save_paper_fn=save_paper_fn,
                exam_keyword=exam_keyword,
                target_exam_date=target_exam_date,
                series_title_prefix=series_title_prefix,
                max_exams=max_exams,
                confirm_total_scores=confirm_total_scores,
                extract_existing_pdfs=extract_existing_pdfs,
                upload_missing_cards=upload_missing_cards,
                replace_unconfirmed_drafts=replace_unconfirmed_drafts,
                use_ai=use_ai,
                archive_exam_id=archive_exam_id,
            )
        _update_job(
            job_id,
            state="completed",
            stage_message="全科补全完成，逐题明细已全部以待人工校对草稿入库。",
            result=result,
        )

    return launch_k12100_job(
        db,
        kind="legacy_collect",
        initial_stage_message="任务已创建，准备启动宿主机持久化浏览器采集…",
        extra_fields={
            "exam_keyword": exam_keyword,
            "confirm_total_scores": confirm_total_scores,
        },
        worker_fn=_worker,
    )
