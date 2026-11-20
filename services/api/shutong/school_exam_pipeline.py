"""本地校考试卷发现、卷头识别、严格匹配、私有归档与本人排名快照服务。

安全边界：
1. 只扫描 `$PAGEBOY_HOME/<env>/school-exams/inbox`（或 CLI 已显式授权的本地目录），
   拒绝符号链接逃逸，导入文件只写入当前环境私有存储；
2. dry-run 不建表、不写文件、不写数据库、不发外部请求；
3. 自动匹配仅接受唯一 EXACT_MATCH；其他结果保留候选与字段差异供人工处理；
4. 排名白名单在递归 PII 清洗之前抽取，独立 append-only 存储，不进入能力画像。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from typing import Any, Protocol
from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import models as m
from . import private_files as files
from .home import (
    HomeIdentityError,
    assert_no_cross_environment_path,
    default_school_exams_dir,
    get_env_home,
    normalize_environment,
    resolve_home_root,
)
from .school_exam_headers import analyze_paper_bytes
from .school_report_parser import classify_report_text
from .school_exam_matcher import (
    ExamIdentity,
    match_exam_identity,
    normalize_grade,
    reports_represent_same_exam,
)

MAX_SCAN_FILES = 200
MAX_SOURCE_DEPTH = 3
ALLOWED_PAPER_SUFFIXES = {
    ".pdf": "application/pdf",
    ".docx": files.DOCX_MEDIA_TYPE,
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}
SOURCE_NOT_CONFIGURED = "SOURCE_NOT_CONFIGURED"
_SCAN_ERROR_MAX = 20
CORE_HEADER_FIELDS = ("academic_year", "grade", "exam_type", "subject", "exam_date")
LEGACY_HEADER_FIELDS = ("school_name", "term", "series_title")


class PaperPipelineError(RuntimeError):
    """可安全回传的流水线错误码，不包含本机绝对路径或敏感内容。"""

    def __init__(self, code: str, message: str = ""):
        super().__init__(code)
        self.code = code
        self.message = message or code


class SchoolPaperSource(Protocol):
    """真实授权卷源适配器接口；未配置时不得伪造远程下载。"""

    name: str

    def configured(self) -> bool: ...

    def acquire(self, inbox: Path) -> list[Path]: ...


# 仓库当前没有已审核、可合法自动获取的学校月考/期中/期末真实卷源。
# 仅登记显式实现并通过授权审查的适配器；空表时 acquire 必须报告 SOURCE_NOT_CONFIGURED。
REGISTERED_SOURCES: dict[str, SchoolPaperSource] = {}


@dataclass(frozen=True)
class SourceStatus:
    environment: str
    inbox_path: Path
    real_source_configured: bool
    ready: bool
    source_code: str | None
    message: str
    directory_display: str | None = None

    def as_public_dict(self) -> dict[str, Any]:
        return {
            "environment": self.environment,
            "directory": str(self.inbox_path),
            "directory_display": self.directory_display or f"$PAGEBOY_HOME/{self.environment}/school-exams/inbox",
            "real_source_configured": self.real_source_configured,
            "source_kind": "local_inbox",
            "ready": self.ready,
            "source_code": self.source_code,
            "message": self.message,
            "supported_formats": ["PDF", "DOCX", "PNG", "JPG/JPEG"],
            "max_file_bytes": files.MAX_BYTES,
        }


def school_exam_storage_root(environment: str | None = None) -> Path:
    env = normalize_environment(environment)
    root = assert_no_cross_environment_path(default_school_exams_dir(env), expected_env=env)
    return root


def school_exam_inbox(environment: str | None = None) -> Path:
    return school_exam_storage_root(environment) / "inbox"


def _assert_directory_mode(path: Path, *, allow_missing: bool = False) -> bool:
    if not path.exists():
        if allow_missing:
            return False
        raise PaperPipelineError("INBOX_NOT_FOUND")
    if path.is_symlink():
        raise PaperPipelineError("INBOX_SYMLINK_REJECTED")
    if not path.is_dir():
        raise PaperPipelineError("INBOX_NOT_DIRECTORY")
    if os.name == "posix":
        mode = path.stat().st_mode & 0o777
        if mode & 0o077:
            raise PaperPipelineError("INBOX_PERMISSIONS_TOO_WIDE", f"目录权限必须为 0700，当前 {mode:04o}")
    return True


def ensure_inbox(environment: str | None = None) -> Path:
    """幂等创建 0700 私有收件箱；已存在但权限过宽时 fail-closed，不静默 chmod 用户目录。"""
    inbox = school_exam_inbox(environment)
    root = inbox.parent
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        current_root_mode = root.stat().st_mode & 0o777
        if current_root_mode & 0o077:
            raise PaperPipelineError("INBOX_PERMISSIONS_TOO_WIDE", f"父目录权限必须为 0700，当前 {current_root_mode:04o}")
    if inbox.exists():
        _assert_directory_mode(inbox)
    else:
        inbox.mkdir(mode=0o700)
    return inbox


def _resolve_scan_target(
    db: Session,
    *,
    owner: str,
    environment: str | None = None,
    exam_id: str | None = None,
) -> tuple[Path, str, str]:
    env = normalize_environment(environment)
    if exam_id:
        exam = db.get(m.SchoolExam, exam_id)
        if exam is not None and exam.learner_id == owner and exam.archive_dir:
            target = files.school_exam_file_path(f"{exam.archive_dir}/exam-paper")
            display = f"$PAGEBOY_HOME/{env}/school-exams/{exam.archive_dir}/exam-paper"
            return target, display, f"{exam.archive_dir}/exam-paper"
    return school_exam_inbox(env), f"$PAGEBOY_HOME/{env}/school-exams/inbox", "inbox"


def inspect_source_status(
    environment: str | None = None,
    *,
    target_dir: Path | None = None,
    directory_display: str | None = None,
) -> SourceStatus:
    env = normalize_environment(environment)
    inbox = target_dir or school_exam_inbox(env)
    try:
        ready = _assert_directory_mode(inbox, allow_missing=True)
        permission_error = None
    except PaperPipelineError as exc:
        ready = False
        permission_error = exc.code
    configured = [name for name, adapter in REGISTERED_SOURCES.items() if adapter.configured()]
    if configured:
        return SourceStatus(
            env,
            inbox,
            True,
            ready,
            None,
            f"已配置授权卷源：{'、'.join(configured)}",
            directory_display=directory_display,
        )
    message = "未配置真实授权学校试卷来源；可扫描当前目录中已有原卷，但不会伪造远程下载。"
    if permission_error:
        message = f"扫描目录权限不安全（{permission_error}）；请仅允许当前用户访问后重试。"
    return SourceStatus(
        env,
        inbox,
        False,
        ready,
        SOURCE_NOT_CONFIGURED,
        message,
        directory_display=directory_display,
    )


def _safe_paper_filename(name: str) -> str:
    cleaned = re.sub(r"[\x00-\x1f\x7f/\\]+", "_", str(name or "")).strip(" .")
    return (cleaned or "paper")[:255]


def _safe_relative_media(path: Path) -> str | None:
    return ALLOWED_PAPER_SUFFIXES.get(path.suffix.lower())


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def iter_source_files(source_dir: Path, *, max_files: int = MAX_SCAN_FILES) -> tuple[list[Path], list[dict[str, str]]]:
    """受限深度遍历来源目录，跳过任何符号链接并报告；不跟随目录链接。"""
    root = Path(source_dir).expanduser()
    if root.is_symlink():
        raise PaperPipelineError("SOURCE_SYMLINK_REJECTED")
    root = root.resolve()
    if not root.is_dir():
        raise PaperPipelineError("SOURCE_NOT_DIRECTORY")
    found: list[Path] = []
    errors: list[dict[str, str]] = []
    base_depth = len(root.parts)
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        if len(current_path.parts) - base_depth > MAX_SOURCE_DEPTH:
            dirnames[:] = []
            continue
        kept_dirs = []
        for name in dirnames:
            candidate = current_path / name
            if candidate.is_symlink():
                errors.append({"path": str(candidate.relative_to(root)), "code": "SYMLINK_REJECTED"})
                continue
            if name.startswith("."):
                continue
            kept_dirs.append(name)
        dirnames[:] = kept_dirs
        for name in sorted(filenames):
            candidate = current_path / name
            if name.startswith("."):
                continue
            if candidate.is_symlink():
                errors.append({"path": str(candidate.relative_to(root)), "code": "SYMLINK_REJECTED"})
                continue
            if _safe_relative_media(candidate) is None:
                errors.append({"path": str(candidate.relative_to(root)), "code": "UNSUPPORTED_FILE_TYPE"})
                continue
            if not _is_within(candidate, root):
                errors.append({"path": str(candidate.relative_to(root)), "code": "PATH_ESCAPE_REJECTED"})
                continue
            found.append(candidate)
            if len(found) >= max_files:
                errors.append({"path": "", "code": "SCAN_FILE_LIMIT_REACHED"})
                return found, errors
    return found, errors


def _read_validated_file(path: Path) -> tuple[bytes, str]:
    media_type = _safe_relative_media(path)
    if media_type is None:
        raise PaperPipelineError("UNSUPPORTED_FILE_TYPE")
    if path.is_symlink():
        raise PaperPipelineError("SYMLINK_REJECTED")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise PaperPipelineError("FILE_READ_FAILED") from exc
    if size <= 0 or size > files.MAX_BYTES:
        raise PaperPipelineError("INVALID_FILE_SIZE")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise PaperPipelineError("FILE_READ_FAILED") from exc
    try:
        files.validate_file(data, media_type)
    except HTTPException as exc:
        raise PaperPipelineError(str(exc.detail or "INVALID_FILE")) from exc
    return data, media_type


def _assert_source_environment_safe(source_dir: Path, environment: str | None) -> Path:
    env = normalize_environment(environment)
    resolved = Path(source_dir).expanduser().resolve()
    try:
        assert_no_cross_environment_path(resolved, expected_env=env)
    except HomeIdentityError as exc:
        raise PaperPipelineError("CROSS_ENVIRONMENT_SOURCE_REJECTED", "拒绝读取其他环境的私有目录") from exc
    home_root = resolve_home_root()
    if resolved == home_root:
        raise PaperPipelineError("CROSS_ENVIRONMENT_SOURCE_REJECTED", "不得把 PAGEBOY_HOME 根目录作为试卷来源")
    return resolved


def preview_local_source(source_dir: Path, *, environment: str | None = None) -> dict[str, Any]:
    """只读预演：验证并识别文件，不创建目录、不写 blob、不写数据库。"""
    path_to_scan = _assert_source_environment_safe(source_dir, environment)
    files_found, path_errors = iter_source_files(path_to_scan)
    rows: list[dict[str, Any]] = []
    errors = list(path_errors)
    for path in files_found:
        try:
            data, media_type = _read_validated_file(path)
            recognition = analyze_paper_bytes(data, media_type, path.name)
            rows.append(
                {
                    "filename": path.name,
                    "sha256": sha256(data).hexdigest(),
                    "media_type": media_type,
                    "byte_size": len(data),
                    "header": recognition.as_dict(),
                    "would_status": "needs_review" if not recognition.complete else "recognized",
                }
            )
        except PaperPipelineError as exc:
            errors.append({"path": path.name, "code": exc.code})
    return {
        "dry_run": True,
        "source": str(path_to_scan),
        "file_count": len(rows),
        "papers": rows,
        "errors": errors[:50],
        "side_effects": "none",
    }


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with NamedTemporaryFile(prefix=".school-exam-", dir=destination.parent, delete=False) as handle:
        temp_path = Path(handle.name)
        handle.write(source.read_bytes())
    try:
        os.chmod(temp_path, 0o600)
        if destination.exists():
            if sha256(destination.read_bytes()).hexdigest() == sha256(temp_path.read_bytes()).hexdigest():
                temp_path.unlink(missing_ok=True)
                return
            raise PaperPipelineError("INBOX_FILENAME_COLLISION")
        os.replace(temp_path, destination)
        os.chmod(destination, 0o600)
    finally:
        temp_path.unlink(missing_ok=True)


def stage_local_source(source_dir: Path, *, environment: str | None = None) -> dict[str, Any]:
    """CLI 专用：把显式授权目录中的合法试卷复制到当前环境 inbox；原文件保持不变。"""
    source_path = _assert_source_environment_safe(source_dir, environment)
    inbox = ensure_inbox(environment)
    if source_path == inbox.resolve():
        raise PaperPipelineError("SOURCE_ALREADY_INBOX", "来源目录已经是当前环境私有收件箱")
    files_found, path_errors = iter_source_files(source_path)
    copied: list[dict[str, Any]] = []
    duplicates = 0
    errors = list(path_errors)
    for path in files_found:
        try:
            data, media_type = _read_validated_file(path)
            digest = sha256(data).hexdigest()
            target = inbox / f"{digest[:12]}_{_safe_paper_filename(path.name)}"
            if target.exists() and sha256(target.read_bytes()).hexdigest() == digest:
                duplicates += 1
                continue
            _atomic_copy(path, target)
            copied.append(
                {
                    "filename": _safe_paper_filename(path.name),
                    "inbox_name": target.name,
                    "sha256": digest,
                    "media_type": media_type,
                }
            )
        except PaperPipelineError as exc:
            errors.append({"path": path.name, "code": exc.code})
    return {
        "source": str(source_path),
        "inbox": str(inbox),
        "staged_count": len(copied),
        "duplicate_count": duplicates,
        "errors": errors[:50],
        "staged": copied,
    }


def acquire_from_configured_source(*, environment: str | None = None) -> dict[str, Any]:
    """调用已登记的真实授权来源；当前无适配器时明确 fail-closed。"""
    ready = [name for name, adapter in REGISTERED_SOURCES.items() if adapter.configured()]
    if not ready:
        raise PaperPipelineError(SOURCE_NOT_CONFIGURED, "未配置真实授权学校试卷来源")
    inbox = ensure_inbox(environment)
    acquired: list[str] = []
    for name in ready:
        for path in REGISTERED_SOURCES[name].acquire(inbox):
            acquired.append(path.name)
    return {"source_adapter": ready, "acquired_count": len(acquired), "files": acquired}


def _exam_identity(exam: m.SchoolExam) -> ExamIdentity:
    return ExamIdentity(
        exam_id=exam.id,
        subject=exam.subject,
        title=exam.title,
        exam_date=str(exam.exam_date),
        grade=exam.grade,
        exam_type=exam.exam_type,
        exam_type_label=exam.exam_type_label,
        academic_year=exam.academic_year,
        external_exam_id=exam.external_exam_id,
    )


def _candidate_exams(db: Session, *, owner: str, subject: str | None) -> list[m.SchoolExam]:
    query = select(m.SchoolExam).where(m.SchoolExam.learner_id == owner)
    if subject:
        query = query.where(m.SchoolExam.subject == subject)
    return db.execute(query.order_by(m.SchoolExam.exam_date.desc(), m.SchoolExam.created_at.desc())).scalars().all()


def run_match_for_paper(db: Session, paper: m.SchoolExamPaper) -> MatchResult:
    header_payload = paper.header_fields or {}
    header = _header_from_paper(paper)
    candidates = _candidate_exams(db, owner=paper.learner_id, subject=header.subject)
    result = match_exam_identity(header, [_exam_identity(item) for item in candidates])
    paper.match_state = result.state
    paper.match_candidates = [item.as_dict() for item in result.candidates]
    if result.state == "EXACT_MATCH" and result.best_exam_id:
        paper.school_exam_id = result.best_exam_id
        paper.status = "matched"
        paper.error_code = None
    else:
        paper.school_exam_id = None
        if paper.status != "imported":
            paper.status = "needs_review"
    paper.updated_at = m.now()
    _ = header_payload
    return result


def _header_value(payload: dict[str, Any], name: str) -> Any:
    value = payload.get(name)
    if isinstance(value, dict):
        return value.get("value")
    return value


def _header_from_paper(paper: m.SchoolExamPaper) -> ExamIdentity:
    fields = paper.header_fields or {}
    values = {
        name: _header_value(fields, name)
        for name in ("subject", "academic_year", "grade", "exam_type", "exam_type_label", "exam_date")
    }
    return ExamIdentity(
        exam_id=None,
        subject=values.get("subject"),
        title=None,
        exam_date=values.get("exam_date"),
        grade=values.get("grade"),
        exam_type=values.get("exam_type"),
        exam_type_label=values.get("exam_type_label"),
        academic_year=values.get("academic_year"),
    )


def _public_header_evidence(fields: dict[str, Any]) -> dict[str, dict[str, Any]]:
    evidence = fields.get("fields") if isinstance(fields.get("fields"), dict) else {}
    public: dict[str, dict[str, Any]] = {}
    for name in CORE_HEADER_FIELDS:
        item = evidence.get(name)
        public[name] = (
            item
            if isinstance(item, dict)
            else {"status": "missing", "value": None, "evidence": "旧版草稿无该字段；请重新执行自动匹配"}
        )
    return public


def _public_header_warnings(fields: dict[str, Any]) -> list[str]:
    warnings = fields.get("warnings")
    if not isinstance(warnings, list):
        return []
    return [
        str(item)
        for item in warnings
        if not any(name in str(item) for name in LEGACY_HEADER_FIELDS)
    ]


def _restore_paper_blob_from_inbox(paper: m.SchoolExamPaper) -> bytes:
    """私有 blob 丢失时，从当前环境 inbox 按 SHA-256 找回原件并补写。"""
    inbox = ensure_inbox()
    found, _ = iter_source_files(inbox)
    for path in found:
        try:
            data, media_type = _read_validated_file(path)
        except PaperPipelineError:
            continue
        if len(data) != paper.byte_size or sha256(data).hexdigest() != paper.sha256:
            continue
        paper.storage_key = files.write_blob(data)
        paper.media_type = media_type
        return data
    raise PaperPipelineError("PAPER_FILE_MISSING")


def _load_paper_bytes_with_recovery(paper: m.SchoolExamPaper) -> bytes:
    """优先读私有 blob；缺失/损坏时从 inbox 恢复。调用方负责 commit。"""
    try:
        path = files.blob_path(paper.storage_key)
        data = path.read_bytes()
        if len(data) == paper.byte_size and sha256(data).hexdigest() == paper.sha256:
            return data
    except (FileNotFoundError, OSError):
        pass
    return _restore_paper_blob_from_inbox(paper)


def _paper_header_public(paper: m.SchoolExamPaper) -> dict[str, Any]:
    fields = paper.header_fields or {}
    return {
        "academic_year": _header_value(fields, "academic_year"),
        "grade": _header_value(fields, "grade"),
        "exam_type": _header_value(fields, "exam_type"),
        "exam_type_label": _header_value(fields, "exam_type_label"),
        "subject": _header_value(fields, "subject"),
        "exam_date": _header_value(fields, "exam_date"),
        "confidence": paper.header_confidence,
        "complete": bool(fields.get("complete")),
        "fields": _public_header_evidence(fields),
        "text_excerpt": paper.header_text or "",
        "text_sha256": fields.get("text_sha256") or "",
        "warnings": _public_header_warnings(fields),
    }


def serialize_paper(paper: m.SchoolExamPaper, exam: m.SchoolExam | None = None) -> dict[str, Any]:
    return {
        "id": paper.id,
        "filename": paper.filename,
        "sha256": paper.sha256,
        "media_type": paper.media_type,
        "byte_size": paper.byte_size,
        "source_kind": paper.source_kind,
        "source_name": paper.source_name,
        "source_ref": paper.source_ref,
        "status": paper.status,
        "match_state": paper.match_state,
        "header": _paper_header_public(paper),
        "candidates": paper.match_candidates or [],
        "school_exam_id": paper.school_exam_id,
        "exam": (
            {
                "id": exam.id,
                "title": exam.title,
                "subject": exam.subject,
                "exam_date": str(exam.exam_date),
                "confirmed_by_user": exam.confirmed_by_user,
            }
            if exam is not None
            else None
        ),
        "error_code": paper.error_code,
        "imported_at": paper.imported_at,
        "created_at": paper.created_at,
        "updated_at": paper.updated_at,
    }


def _scan_errors(errors: list[dict[str, str]]) -> list[dict[str, str]]:
    return errors[:_SCAN_ERROR_MAX]


def scan_local_papers(
    db: Session,
    *,
    owner: str,
    environment: str | None = None,
    apply_imports: bool = False,
    source_kind: str = "local_scan",
    exam_id: str | None = None,
) -> dict[str, Any]:
    """扫描当前环境校考目录（优先选中档案 exam-paper/，否则 inbox/）并登记发现；apply_imports 仅处理唯一精确匹配。"""
    target_dir, directory_display, source_label = _resolve_scan_target(
        db,
        owner=owner,
        environment=environment,
        exam_id=exam_id,
    )
    if source_label == "inbox":
        inbox = ensure_inbox(environment)
    else:
        exam = db.get(m.SchoolExam, exam_id)
        files.ensure_school_exam_archive_dirs(exam.archive_dir)
        _assert_directory_mode(target_dir, allow_missing=False)
        inbox = target_dir
    status = inspect_source_status(environment, target_dir=inbox, directory_display=directory_display)
    run = m.SchoolExamScanRun(
        learner_id=owner,
        source_kind=source_kind,
        source_label=source_label[:80],
        status="running",
        started_at=m.now(),
    )
    db.add(run)
    db.flush()

    found, path_errors = iter_source_files(inbox)
    errors: list[dict[str, str]] = _scan_errors(path_errors)
    discovered = duplicate = invalid = needs_review = imported = 0
    papers: list[m.SchoolExamPaper] = []

    for path in found:
        discovered += 1
        try:
            data, media_type = _read_validated_file(path)
            digest = sha256(data).hexdigest()
            existing = db.execute(
                select(m.SchoolExamPaper).where(
                    m.SchoolExamPaper.learner_id == owner,
                    m.SchoolExamPaper.sha256 == digest,
                )
            ).scalars().first()
            if existing is not None:
                duplicate += 1
                existing_path = files.blob_path(existing.storage_key)
                if not existing_path.is_file():
                    existing.storage_key = files.write_blob(data)
                    existing.media_type = media_type
                papers.append(existing)
                continue
            recognition = analyze_paper_bytes(data, media_type, path.name)
            report_kind, _ = classify_report_text(recognition.text_excerpt)
            if "分析报告册" in (recognition.text_excerpt or "") or report_kind == "exam_analysis_report":
                # 分析报告册由报告扫描入口处理，绝不能当成单科试卷建档。
                continue
            storage_key = files.write_blob(data)
            paper = m.SchoolExamPaper(
                learner_id=owner,
                sha256=digest,
                filename=_safe_paper_filename(path.name),
                media_type=media_type,
                byte_size=len(data),
                storage_key=storage_key,
                source_kind=source_kind,
                source_name=source_label[:80],
                source_ref=f"{source_label}/{_safe_paper_filename(path.relative_to(inbox).as_posix())}"[:255],
                header_text=recognition.text_excerpt,
                header_fields={**recognition.as_dict(), "complete": recognition.complete},
                header_confidence=recognition.confidence,
                status="needs_review",
                match_state="NEEDS_REVIEW",
            )
            db.add(paper)
            db.flush()
            if not recognition.complete:
                needs_review += 1
                paper.match_state = "NEEDS_REVIEW"
                paper.match_candidates = []
                paper.updated_at = m.now()
            else:
                result = run_match_for_paper(db, paper)
                if result.state != "EXACT_MATCH":
                    needs_review += 1
                if apply_imports and result.state == "EXACT_MATCH":
                    import_matched_paper(db, paper=paper, owner=owner)
                    imported += 1
            papers.append(paper)
        except PaperPipelineError as exc:
            invalid += 1
            errors.append({"path": path.name, "code": exc.code})
        except HTTPException as exc:
            invalid += 1
            errors.append({"path": path.name, "code": str(exc.detail or "INVALID_PAPER")})
        except Exception:
            invalid += 1
            errors.append({"path": path.name, "code": "PAPER_INGEST_FAILED"})
        finally:
            _ = status

    run.discovered_count = discovered
    run.imported_count = imported
    run.duplicate_count = duplicate
    run.invalid_count = invalid
    run.needs_review_count = needs_review
    run.error_count = len(errors)
    run.errors = errors
    run.status = "completed"
    run.finished_at = m.now()
    db.commit()
    for paper in papers:
        db.refresh(paper)
    return {
        "run": {
            "id": run.id,
            "status": run.status,
            "source_label": run.source_label,
            "discovered_count": discovered,
            "imported_count": imported,
            "duplicate_count": duplicate,
            "invalid_count": invalid,
            "needs_review_count": needs_review,
            "error_count": len(errors),
            "errors": errors,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
        },
        "papers": [serialize_paper(item) for item in papers],
        "source": status.as_public_dict(),
    }


def latest_scan_run(db: Session, *, owner: str) -> m.SchoolExamScanRun | None:
    return db.execute(
        select(m.SchoolExamScanRun)
        .where(m.SchoolExamScanRun.learner_id == owner)
        .order_by(m.SchoolExamScanRun.started_at.desc(), m.SchoolExamScanRun.id.desc())
    ).scalars().first()


_SCHOOL_SUBJECT_ORDER = ("chinese", "math", "english", "physics", "ethics")
_SCHOOL_SUBJECT_CN = {
    "chinese": "语文",
    "math": "数学",
    "english": "英语",
    "physics": "物理",
    "ethics": "道德与法治",
}


def _evaluate_report_completeness(
    report: m.SchoolExamReport,
    by_subj: dict[str, m.SchoolExam],
    item_counts: dict[str, dict[str, int]],
    attachment_counts: dict[str, int],
    rank_keys_by_exam: dict[str, set[tuple[str, str]]],
) -> dict[str, Any]:
    missing: list[str] = []
    if not report.exam_date:
        missing.append("考试日期")

    subjects_list = [item for item in (report.subjects or []) if isinstance(item, dict)]
    question_subjs = {str(q.get("subject") or "") for q in (report.questions or []) if isinstance(q, dict) and q.get("subject")}
    card_subjs = {str(k) for k, pages in (report.answer_card_pages or {}).items() if pages}
    has_total_rank = report.total_class_rank is not None or report.total_grade_rank is not None

    for item in subjects_list:
        subj = str(item.get("subject") or "").strip()
        if subj not in _SCHOOL_SUBJECT_CN:
            continue
        cn = _SCHOOL_SUBJECT_CN[subj]
        ex = by_subj.get(subj)
        if ex is None:
            missing.append(f"{cn}建档")
            continue
        if subj in question_subjs:
            cnt = item_counts.get(ex.id, {"draft": 0, "confirmed": 0})
            if cnt["draft"] + cnt["confirmed"] == 0:
                missing.append(f"{cn}逐题")
        if subj in card_subjs and attachment_counts.get(ex.id, 0) == 0:
            missing.append(f"{cn}答题卡")
        exam_ranks = rank_keys_by_exam.get(ex.id, set())
        if item.get("class_rank") is not None and (subj, "class") not in exam_ranks:
            missing.append(f"{cn}班排")
        if item.get("grade_rank") is not None and (subj, "grade") not in exam_ranks:
            missing.append(f"{cn}年排")
        if item.get("class_highest") is not None and ex.class_highest is None:
            missing.append(f"{cn}班最高")
        if item.get("grade_highest") is not None and ex.grade_highest is None:
            missing.append(f"{cn}年最高")
        if has_total_rank:
            if report.total_class_rank is not None and ("total", "class") not in exam_ranks:
                if "总分排名" not in missing:
                    missing.append("总分排名")
            if report.total_grade_rank is not None and ("total", "grade") not in exam_ranks:
                if "总分排名" not in missing:
                    missing.append("总分排名")

    return {"complete": len(missing) == 0 and bool(subjects_list), "missing": missing}


def select_canonical_reports(all_reports: list[m.SchoolExamReport]) -> list[m.SchoolExamReport]:
    """按读写同源的同场等价规则无副作用归并报告（读路径去重与持久化共用一套口径）。"""
    clusters: list[list[m.SchoolExamReport]] = []
    for rep in all_reports:
        rep_links = [
            str(link.get("exam_id") or "")
            for link in (rep.linked_exam_ids or [])
            if isinstance(link, dict) and link.get("exam_id")
        ]
        placed = False
        for grp in clusters:
            if any(
                reports_represent_same_exam(
                    a_ext_id=rep.external_exam_id,
                    a_year=rep.academic_year,
                    a_grade=rep.grade,
                    a_type=rep.exam_type,
                    a_seq=rep.exam_sequence,
                    a_title=rep.title,
                    a_date=rep.exam_date,
                    a_linked_ids=rep_links,
                    b=anchor,
                )
                for anchor in grp
            ):
                grp.append(rep)
                placed = True
                break
        if not placed:
            clusters.append([rep])

    winners: list[m.SchoolExamReport] = []
    for grp in clusters:
        grp.sort(
            key=lambda r: (
                bool(r.external_exam_id),
                len(r.subjects or []),
                len(r.questions or []),
                r.pages or 0,
                bool(r.exam_date),
                r.created_at.isoformat() if r.created_at else "",
            ),
            reverse=True,
        )
        winners.append(grp[0])
    return sorted(
        winners,
        key=lambda r: (
            str(r.exam_date or ""),
            r.created_at.isoformat() if r.created_at else "",
            r.id,
        ),
        reverse=True,
    )


def _serialize_synced_reports(db: Session, *, owner: str) -> list[dict[str, Any]]:
    """从数据库读取已同步的 k12100/报告册及其关联各科实时档案状态，避免依赖易失任务内存。"""
    all_reports = [
        report
        for report in db.execute(
            select(m.SchoolExamReport).where(m.SchoolExamReport.learner_id == owner)
        ).scalars().all()
        if report.external_exam_id
        or str(report.source_ref or "").startswith("k12100/")
        or bool(report.linked_exam_ids)
    ]
    if not all_reports:
        return []

    reports = select_canonical_reports(all_reports)

    linked_ids = {
        str(link.get("exam_id") or "").strip()
        for r in reports
        for link in (r.linked_exam_ids or [])
        if isinstance(link, dict) and link.get("exam_id")
    }
    ext_ids = {str(r.external_exam_id).strip() for r in reports if r.external_exam_id}

    exam_filters = []
    if linked_ids:
        exam_filters.append(m.SchoolExam.id.in_(linked_ids))
    if ext_ids:
        exam_filters.append(m.SchoolExam.external_exam_id.in_(ext_ids))
    exams = (
        db.execute(
            select(m.SchoolExam).where(
                m.SchoolExam.learner_id == owner,
                or_(*exam_filters),
            )
        ).scalars().all()
        if exam_filters
        else []
    )
    exams_by_id = {exam.id: exam for exam in exams}
    exams_by_ext: dict[str, list[m.SchoolExam]] = {}
    for exam in exams:
        if exam.external_exam_id:
            exams_by_ext.setdefault(exam.external_exam_id, []).append(exam)

    fetched_ids = list(exams_by_id.keys())
    item_counts: dict[str, dict[str, int]] = {}
    attachment_counts: dict[str, int] = {}
    rank_keys_by_exam: dict[str, set[tuple[str, str]]] = {}
    if fetched_ids:
        for exam_id, confirmed, cnt in db.execute(
            select(
                m.SchoolExamItem.school_exam_id,
                m.SchoolExamItem.confirmed_by_user,
                func.count(m.SchoolExamItem.id),
            )
            .where(m.SchoolExamItem.school_exam_id.in_(fetched_ids))
            .group_by(m.SchoolExamItem.school_exam_id, m.SchoolExamItem.confirmed_by_user)
        ).all():
            bucket = item_counts.setdefault(exam_id, {"draft": 0, "confirmed": 0})
            bucket["confirmed" if confirmed else "draft"] += int(cnt or 0)
        for exam_id, cnt in db.execute(
            select(
                m.SchoolPaperAttachment.school_exam_id,
                func.count(m.SchoolPaperAttachment.id),
            )
            .where(m.SchoolPaperAttachment.school_exam_id.in_(fetched_ids))
            .group_by(m.SchoolPaperAttachment.school_exam_id)
        ).all():
            attachment_counts[exam_id] = int(cnt or 0)
        for exam_id, s_scope, r_scope in db.execute(
            select(
                m.SchoolExamRankSnapshot.school_exam_id,
                m.SchoolExamRankSnapshot.subject_scope,
                m.SchoolExamRankSnapshot.scope,
            ).where(m.SchoolExamRankSnapshot.school_exam_id.in_(fetched_ids))
        ).all():
            rank_keys_by_exam.setdefault(exam_id, set()).add((str(s_scope), str(r_scope)))

    subj_rank = {code: idx for idx, code in enumerate(_SCHOOL_SUBJECT_ORDER)}
    out: list[dict[str, Any]] = []
    for report in reports:
        by_subj: dict[str, m.SchoolExam] = {}
        report_subj_map = {
            str(entry.get("subject") or ""): entry
            for entry in (report.subjects or [])
            if isinstance(entry, dict) and entry.get("subject")
        }
        for link in report.linked_exam_ids or []:
            if not isinstance(link, dict):
                continue
            exam = exams_by_id.get(str(link.get("exam_id") or ""))
            if exam is not None:
                link_subj = str(link.get("subject") or "").strip()
                if exam.subject == "all" and link_subj and link_subj in _SCHOOL_SUBJECT_CN:
                    by_subj.setdefault(link_subj, exam)
                else:
                    by_subj.setdefault(exam.subject, exam)
        if report.external_exam_id:
            for exam in exams_by_ext.get(report.external_exam_id, []):
                if exam.subject == "all":
                    for subj_code in report_subj_map:
                        if subj_code in _SCHOOL_SUBJECT_CN:
                            by_subj.setdefault(subj_code, exam)
                else:
                    by_subj.setdefault(exam.subject, exam)

        sorted_items = sorted(
            by_subj.items(),
            key=lambda pair: (subj_rank.get(pair[0], 99), pair[0], pair[1].id),
        )
        exams_out = []
        for subj_code, ex in sorted_items:
            s_entry = report_subj_map.get(subj_code, {})
            subj_rank_keys = rank_keys_by_exam.get(ex.id, set())
            rank_synced_count = sum(1 for sc, _ in subj_rank_keys if sc == subj_code)
            is_all_archive = ex.subject == "all"
            subj_earned = s_entry.get("score") if is_all_archive and s_entry.get("score") is not None else ex.earned_points
            subj_max = s_entry.get("max_score") if is_all_archive and s_entry.get("max_score") is not None else ex.max_points
            subj_confirmed = bool(s_entry.get("confirmed_by_user")) if is_all_archive else bool(ex.confirmed_by_user)
            exams_out.append(
                {
                    "exam_id": ex.id,
                    "subject": subj_code,
                    "subject_label": _SCHOOL_SUBJECT_CN.get(subj_code, subj_code),
                    "exam_title": ex.title,
                    "exam_date": str(ex.exam_date),
                    "earned_points": subj_earned,
                    "max_points": subj_max,
                    "confirmed_by_user": subj_confirmed,
                    "draft_count": item_counts.get(ex.id, {}).get("draft", 0),
                    "confirmed_item_count": item_counts.get(ex.id, {}).get("confirmed", 0),
                    "attachment_count": attachment_counts.get(ex.id, 0),
                    "class_rank": s_entry.get("class_rank"),
                    "grade_rank": s_entry.get("grade_rank"),
                    "participants": s_entry.get("participants"),
                    "class_highest": (
                        s_entry.get("class_highest")
                        if is_all_archive
                        else (ex.class_highest if ex.class_highest is not None else s_entry.get("class_highest"))
                    ),
                    "grade_highest": (
                        s_entry.get("grade_highest")
                        if is_all_archive
                        else (ex.grade_highest if ex.grade_highest is not None else s_entry.get("grade_highest"))
                    ),
                    "rank_synced_count": rank_synced_count,
                }
            )
        seen_subjs = {subj_code for subj_code, _ in sorted_items}
        unlinked_subjects: list[dict[str, Any]] = []
        seen_unlinked: set[str] = set()
        for entry in report.subjects or []:
            if not isinstance(entry, dict):
                continue
            subj = str(entry.get("subject") or "").strip()
            if not subj or subj in seen_subjs or subj in seen_unlinked or subj not in _SCHOOL_SUBJECT_CN:
                continue
            seen_unlinked.add(subj)
            unlinked_subjects.append(
                {
                    "subject": subj,
                    "subject_label": _SCHOOL_SUBJECT_CN[subj],
                    "score": entry.get("score"),
                    "max_score": entry.get("max_score"),
                }
            )

        completeness = _evaluate_report_completeness(
            report,
            by_subj,
            item_counts,
            attachment_counts,
            rank_keys_by_exam,
        )
        out.append(
            {
                "id": report.id,
                "title": report.title,
                "external_exam_id": report.external_exam_id,
                "exam_date": report.exam_date,
                "academic_year": report.academic_year,
                "grade": normalize_grade(report.grade) or report.grade,
                "exam_type": report.exam_type,
                "status": report.status,
                "match_state": report.match_state,
                "report_total_score": report.report_total_score,
                "report_total_max": report.report_total_max,
                "total_class_rank": report.total_class_rank,
                "total_grade_rank": report.total_grade_rank,
                "total_participants": report.total_participants,
                "total_class_highest": report.total_class_highest,
                "total_grade_highest": report.total_grade_highest,
                "pages": report.pages,
                "updated_at": report.updated_at.isoformat() if report.updated_at else None,
                "exams": exams_out,
                "unlinked_subjects": unlinked_subjects,
                "completeness": completeness,
            }
        )
    return out


def _sync_readiness(synced_reports: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(synced_reports)
    complete = sum(1 for item in synced_reports if item.get("completeness", {}).get("complete"))
    return {
        "total_reports": total,
        "complete_reports": complete,
        "incomplete_reports": total - complete,
        "all_complete": total > 0 and complete == total,
    }


def get_sync_center(
    db: Session,
    *,
    owner: str,
    environment: str | None = None,
    exam_id: str | None = None,
) -> dict[str, Any]:
    target_dir, directory_display, _ = _resolve_scan_target(
        db,
        owner=owner,
        environment=environment,
        exam_id=exam_id,
    )
    status = inspect_source_status(environment, target_dir=target_dir, directory_display=directory_display)
    run = latest_scan_run(db, owner=owner)
    papers = db.execute(
        select(m.SchoolExamPaper)
        .where(m.SchoolExamPaper.learner_id == owner)
        .order_by(m.SchoolExamPaper.created_at.desc(), m.SchoolExamPaper.id.desc())
    ).scalars().all()
    exam_ids = {item.school_exam_id for item in papers if item.school_exam_id}
    exams = {
        item.id: item
        for item in db.execute(select(m.SchoolExam).where(m.SchoolExam.id.in_(exam_ids))).scalars().all()
    } if exam_ids else {}
    counts = {
        "total": len(papers),
        "needs_review": sum(1 for item in papers if item.status == "needs_review"),
        "matched": sum(1 for item in papers if item.status == "matched"),
        "imported": sum(1 for item in papers if item.status == "imported"),
        "rejected": sum(1 for item in papers if item.status == "rejected"),
    }
    synced_reports = _serialize_synced_reports(db, owner=owner)
    return {
        "source": status.as_public_dict(),
        "latest_scan": (
            {
                "id": run.id,
                "status": run.status,
                "discovered_count": run.discovered_count,
                "imported_count": run.imported_count,
                "duplicate_count": run.duplicate_count,
                "invalid_count": run.invalid_count,
                "needs_review_count": run.needs_review_count,
                "error_count": run.error_count,
                "errors": run.errors or [],
                "started_at": run.started_at,
                "finished_at": run.finished_at,
            }
            if run is not None
            else None
        ),
        "counts": counts,
        "papers": [serialize_paper(item, exams.get(item.school_exam_id or "")) for item in papers],
        "synced_reports": synced_reports,
        "sync_readiness": _sync_readiness(synced_reports),
    }


def reanalyze_paper_header(db: Session, *, paper: m.SchoolExamPaper) -> dict[str, Any]:
    """重新读取私有原件并识别五字段卷头；用于修复旧版持久化草稿。"""
    if paper.status == "imported":
        raise HTTPException(409, detail="PAPER_ALREADY_IMPORTED")
    data = _load_paper_bytes_with_recovery(paper)
    try:
        files.validate_file(data, paper.media_type)
    except HTTPException as exc:
        raise PaperPipelineError(str(exc.detail or "INVALID_PAPER")) from exc
    recognition = analyze_paper_bytes(data, paper.media_type, paper.filename)
    paper.header_text = recognition.text_excerpt
    paper.header_fields = {**recognition.as_dict(), "complete": recognition.complete}
    paper.header_confidence = recognition.confidence
    paper.status = "needs_review"
    paper.school_exam_id = None
    paper.match_candidates = []
    paper.error_code = None
    paper.updated_at = m.now()
    result = run_match_for_paper(db, paper)
    db.commit()
    db.refresh(paper)
    return {"paper": serialize_paper(paper), "match": result.as_dict()}


def rematch_paper(db: Session, *, paper: m.SchoolExamPaper) -> dict[str, Any]:
    """重新读取原件、重识别五字段，再做严格匹配（修复旧草稿的唯一入口）。"""
    if paper.status == "imported":
        raise HTTPException(409, detail="PAPER_ALREADY_IMPORTED")
    return reanalyze_paper_header(db, paper=paper)


def manual_match_paper(
    db: Session,
    *,
    paper: m.SchoolExamPaper,
    owner: str,
    exam_id: str,
    confirmed_by_human: bool,
) -> dict[str, Any]:
    if not confirmed_by_human:
        raise HTTPException(422, detail="HUMAN_CONFIRMATION_REQUIRED")
    if paper.status == "imported":
        raise HTTPException(409, detail="PAPER_ALREADY_IMPORTED")
    exam = db.get(m.SchoolExam, exam_id)
    if exam is None or exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")
    header = _header_from_paper(paper)
    if header.subject and header.subject != exam.subject:
        raise HTTPException(409, detail="SCHOOL_EXAM_SUBJECT_MISMATCH")
    paper.school_exam_id = exam.id
    paper.match_state = "MANUAL_CONFIRMED"
    paper.match_candidates = [
        {
            "exam_id": exam.id,
            "title": exam.title,
            "exam_date": str(exam.exam_date),
            "manual": True,
            "confirmed_by_human": True,
        }
    ]
    paper.status = "matched"
    paper.error_code = None
    paper.updated_at = m.now()
    db.commit()
    db.refresh(paper)
    return {"paper": serialize_paper(paper, exam)}


def _load_private_paper(paper: m.SchoolExamPaper) -> bytes:
    path = files.blob_path(paper.storage_key)
    if not path.is_file() or path.is_symlink():
        raise HTTPException(409, detail="PAPER_FILE_MISSING")
    data = path.read_bytes()
    if len(data) != paper.byte_size or sha256(data).hexdigest() != paper.sha256:
        raise HTTPException(409, detail="PAPER_HASH_MISMATCH")
    return data


def _fill_exam_identity(exam: m.SchoolExam, header: ExamIdentity) -> list[str]:
    """仅填补空字段；绝不覆盖已存在的考试身份或总分。"""
    changed: list[str] = []
    for name in ("grade", "exam_type", "exam_type_label", "academic_year"):
        if getattr(exam, name):
            continue
        value = getattr(header, name)
        if value:
            limit = 40 if name == "exam_type_label" else 20
            setattr(exam, name, str(value)[:limit])
            changed.append(name)
    return changed


def import_matched_paper(db: Session, *, paper: m.SchoolExamPaper, owner: str) -> dict[str, Any]:
    if paper.status == "imported":
        exam = db.get(m.SchoolExam, paper.school_exam_id) if paper.school_exam_id else None
        return {"already_imported": True, "paper": serialize_paper(paper, exam), "attachment_created": False}
    if paper.status != "matched" or not paper.school_exam_id:
        raise HTTPException(409, detail="SCHOOL_EXAM_MATCH_REQUIRED")
    exam = db.get(m.SchoolExam, paper.school_exam_id)
    if exam is None or exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")
    _load_private_paper(paper)

    existing = db.execute(
        select(m.SchoolPaperAttachment).where(
            m.SchoolPaperAttachment.school_exam_id == exam.id,
            m.SchoolPaperAttachment.owner_id == owner,
            m.SchoolPaperAttachment.sha256 == paper.sha256,
        )
    ).scalars().first()
    created = False
    if existing is None:
        attachment = m.SchoolPaperAttachment(
            school_exam_id=exam.id,
            owner_id=owner,
            filename=paper.filename,
            media_type=paper.media_type,
            sha256=paper.sha256,
            byte_size=paper.byte_size,
            storage_key=paper.storage_key,
        )
        db.add(attachment)
        existing = attachment
        created = True
    identity_updates = _fill_exam_identity(exam, _header_from_paper(paper))
    paper.status = "imported"
    paper.imported_at = m.now()
    paper.updated_at = m.now()
    paper.error_code = None
    db.commit()
    db.refresh(paper)
    db.refresh(exam)
    if created:
        db.refresh(existing)
    return {
        "already_imported": False,
        "paper": serialize_paper(paper, exam),
        "attachment_created": created,
        "attachment": {
            "id": existing.id,
            "filename": existing.filename,
            "media_type": existing.media_type,
            "sha256": existing.sha256,
            "byte_size": existing.byte_size,
        },
        "metadata_updates": identity_updates,
    }


_RANK_PRIMARY_FIELDS: tuple[tuple[str, str], ...] = (
    ("classrank", "class"),
    ("class_rank", "class"),
    ("graderank", "grade"),
    ("grade_rank", "grade"),
    ("schoolrank", "school"),
    ("school_rank", "school"),
    ("examrank", "school"),
    ("exam_rank", "school"),
    ("regionrank", "region"),
    ("region_rank", "region"),
)
_RANK_COUNT_FIELDS: dict[str, tuple[str, ...]] = {
    "class": ("classstudentnum", "classnum", "classcount", "classtotal", "classrankcount"),
    "grade": ("gradestudentnum", "gradenum", "gradecount", "gradetotal", "graderankcount"),
    "school": (
        "schoolstudentnum",
        "schoolnum",
        "schoolcount",
        "schooltotal",
        "examnum",
        "actualexamnum",
        "examstudentnum",
    ),
    "region": ("regionstudentnum", "regionnum", "regioncount", "regiontotal"),
}
_RANK_RATE_FIELDS: dict[str, tuple[str, ...]] = {
    "class": ("classrankrate",),
    "grade": ("graderankrate",),
    "school": ("schoolrankrate", "examrankrate"),
    "region": ("regionrankrate",),
}


def _parse_rank_value(value: Any) -> tuple[int | None, int | None]:
    if isinstance(value, bool) or value is None:
        return None, None
    if isinstance(value, (int, float)):
        number = int(value)
        return (number, None) if number > 0 and float(value).is_integer() else (None, None)
    text = str(value).strip()
    if not text:
        return None, None
    match = re.fullmatch(r"第?\s*(\d+)\s*(?:名|/|／)\s*(\d+)?\s*名?", text)
    if match:
        return int(match.group(1)), int(match.group(2)) if match.group(2) else None
    match = re.fullmatch(r"第?\s*(\d+)\s*名?", text)
    if match:
        return int(match.group(1)), None
    return None, None


def _parse_participant_count(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = int(value)
        return number if number > 0 and float(value).is_integer() else None
    match = re.fullmatch(r"\s*(\d+)\s*(?:人|名)?\s*", str(value))
    return int(match.group(1)) if match else None


def _parse_percentile(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("%"):
            number = float(text[:-1]) / 100.0
        else:
            number = float(text)
    except ValueError:
        return None
    if 0 < number <= 1:
        return round(number, 6)
    if 1 < number <= 100:
        return round(number / 100.0, 6)
    return None


def _scalar_rank_sources(raw_subject: dict[str, Any]) -> dict[str, Any]:
    sources: dict[str, Any] = {str(key).lower(): value for key, value in raw_subject.items()}
    for nested_key in ("rank", "rankInfo", "studentRank", "myRank"):
        nested = raw_subject.get(nested_key)
        if isinstance(nested, dict):
            sources.update({str(key).lower(): value for key, value in nested.items()})
    return sources


def extract_own_rank_entries(raw_subject: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """在 PII 清洗前仅抽取本人单值排名白名单；不读取任何学生列表。"""
    if not isinstance(raw_subject, dict):
        return [], [{"scope": "unknown", "code": "RANK_SOURCE_INVALID"}]
    sources = _scalar_rank_sources(raw_subject)
    by_scope: dict[str, list[dict[str, Any]]] = {}
    issues: list[dict[str, str]] = []

    for field_name, scope in _RANK_PRIMARY_FIELDS:
        if field_name.lower() not in sources:
            continue
        raw_value = sources[field_name.lower()]
        if raw_value is None or str(raw_value).strip() == "":
            continue
        rank_value, embedded_count = _parse_rank_value(raw_value)
        if rank_value is None:
            issues.append({"scope": scope, "code": "RANK_VALUE_INVALID", "field": field_name})
            continue
        count: int | None = embedded_count
        for count_name in _RANK_COUNT_FIELDS[scope]:
            if count_name in sources:
                parsed_count = _parse_participant_count(sources[count_name])
                if parsed_count is not None:
                    count = parsed_count
                    break
        if count is not None and rank_value > count:
            issues.append({"scope": scope, "code": "RANK_EXCEEDS_PARTICIPANT_COUNT", "field": field_name})
            continue
        percentile = None
        for rate_name in _RANK_RATE_FIELDS[scope]:
            if rate_name in sources:
                percentile = _parse_percentile(sources[rate_name])
                if percentile is not None:
                    break
        by_scope.setdefault(scope, []).append(
            {
                "scope": scope,
                "rank_value": rank_value,
                "participant_count": count,
                "percentile": percentile,
                "source_field": field_name,
            }
        )

    entries: list[dict[str, Any]] = []
    for scope, values in by_scope.items():
        distinct = {(item["rank_value"], item["participant_count"], item["percentile"]) for item in values}
        if len(distinct) > 1:
            issues.append({"scope": scope, "code": "RANK_SOURCE_CONFLICT", "field": values[0]["source_field"]})
            continue
        entries.append(values[0])
    return entries, issues


def persist_rank_entries(
    db: Session,
    *,
    exam: m.SchoolExam,
    owner: str,
    subject_scope: str,
    entries: list[dict[str, Any]],
    source_name: str = "k12100",
    ownership_status: str = "unverified",
    ownership_basis: str | None = None,
    captured_at: datetime | None = None,
) -> list[m.SchoolExamRankSnapshot]:
    """append-only 写入；只有已确认归属本人的排名才可进入快照。"""
    if ownership_status != "verified":
        return []
    captured = captured_at or m.now()
    created: list[m.SchoolExamRankSnapshot] = []
    for entry in entries:
        payload = {
            "scope": entry["scope"],
            "rank_value": entry["rank_value"],
            "participant_count": entry.get("participant_count"),
            "percentile": entry.get("percentile"),
            "source_field": entry["source_field"],
        }
        digest = sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        existing = db.execute(
            select(m.SchoolExamRankSnapshot).where(
                m.SchoolExamRankSnapshot.school_exam_id == exam.id,
                m.SchoolExamRankSnapshot.subject_scope == subject_scope,
                m.SchoolExamRankSnapshot.scope == entry["scope"],
                m.SchoolExamRankSnapshot.source_field == entry["source_field"],
                m.SchoolExamRankSnapshot.content_hash == digest,
            )
        ).scalars().first()
        if existing is not None:
            if existing.highest_score is None and entry.get("highest_score") is not None:
                existing.highest_score = float(entry["highest_score"])
            continue
        record = m.SchoolExamRankSnapshot(
            school_exam_id=exam.id,
            learner_id=owner,
            subject_scope=subject_scope,
            scope=entry["scope"],
            rank_value=int(entry["rank_value"]),
            participant_count=entry.get("participant_count"),
            percentile=entry.get("percentile"),
            highest_score=float(entry["highest_score"]) if entry.get("highest_score") is not None else None,
            source_name=source_name,
            source_field=entry["source_field"],
            content_hash=digest,
            ownership_status="verified",
            ownership_basis=(ownership_basis or "verified_self_response")[:64],
            review_status="pending",
            captured_at=captured,
        )
        db.add(record)
        created.append(record)
    if created:
        db.flush()
    return created


def _serialize_rank_rows(rows: list[m.SchoolExamRankSnapshot]) -> tuple[list[dict[str, Any]], set[str]]:
    latest: dict[str, m.SchoolExamRankSnapshot] = {}
    history_counts: dict[str, int] = {}
    for row in rows:
        history_counts[row.scope] = history_counts.get(row.scope, 0) + 1
        latest.setdefault(row.scope, row)
    order = {"class": 1, "grade": 2, "school": 3, "region": 4}
    serialized = [
        {
            "id": row.id,
            "subject_scope": row.subject_scope,
            "scope": row.scope,
            "rank_value": row.rank_value,
            "participant_count": row.participant_count,
            "percentile": row.percentile,
            "highest_score": row.highest_score,
            "source_name": row.source_name,
            "source_field": row.source_field,
            "ownership_status": row.ownership_status,
            "ownership_basis": row.ownership_basis,
            "review_status": row.review_status,
            "captured_at": row.captured_at,
            "history_count": history_counts.get(row.scope, 0),
        }
        for row in sorted(latest.values(), key=lambda item: order.get(item.scope, 9))
    ]
    return serialized, set(latest.keys())


def rank_payload(db: Session, *, exam: m.SchoolExam, owner: str) -> dict[str, Any]:
    if exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")
    rows = db.execute(
        select(m.SchoolExamRankSnapshot)
        .where(m.SchoolExamRankSnapshot.school_exam_id == exam.id)
        .order_by(m.SchoolExamRankSnapshot.captured_at.desc(), m.SchoolExamRankSnapshot.created_at.desc())
    ).scalars().all()
    subject_rows = [row for row in rows if row.subject_scope != "total"]
    total_rows = [row for row in rows if row.subject_scope == "total"]
    primary_rows = subject_rows if subject_rows else rows
    serialized, present_scopes = _serialize_rank_rows(primary_rows)
    total_serialized, _ = _serialize_rank_rows(total_rows)

    linked_report: m.SchoolExamReport | None = None
    if exam.external_exam_id:
        linked_report = db.execute(
            select(m.SchoolExamReport).where(
                m.SchoolExamReport.learner_id == owner,
                m.SchoolExamReport.external_exam_id == exam.external_exam_id,
            )
        ).scalars().first()
    if linked_report is None:
        for cand in db.execute(select(m.SchoolExamReport).where(m.SchoolExamReport.learner_id == owner)).scalars().all():
            if any(isinstance(l, dict) and l.get("exam_id") == exam.id for l in (cand.linked_exam_ids or [])):
                linked_report = cand
                break

    return {
        "exam_id": exam.id,
        "class_highest": exam.class_highest,
        "grade_highest": exam.grade_highest,
        "ranks": serialized,
        "total_ranks": total_serialized,
        "report_total": (
            {
                "report_total_score": linked_report.report_total_score,
                "report_total_max": linked_report.report_total_max,
                "total_class_rank": linked_report.total_class_rank,
                "total_grade_rank": linked_report.total_grade_rank,
                "total_participants": linked_report.total_participants,
                "total_class_highest": linked_report.total_class_highest,
                "total_grade_highest": linked_report.total_grade_highest,
            }
            if linked_report is not None
            else None
        ),
        "missing_scopes": [scope for scope in ("class", "grade", "school", "region") if scope not in present_scopes],
        "disclaimer": "本人排名仅为平台来源快照，不进入知识点能力画像，也不预测中考成绩。",
    }


def confirm_rank(db: Session, *, rank_id: str, owner: str, exam_id: str) -> dict[str, Any]:
    rank = db.get(m.SchoolExamRankSnapshot, rank_id)
    if rank is None or rank.school_exam_id != exam_id or rank.learner_id != owner:
        raise HTTPException(404, detail="rank not found")
    if rank.ownership_status != "verified":
        raise HTTPException(409, detail="RANK_OWNERSHIP_UNVERIFIED")
    if rank.review_status != "confirmed":
        rank.review_status = "confirmed"
        db.commit()
        db.refresh(rank)
    return {
        "id": rank.id,
        "scope": rank.scope,
        "rank_value": rank.rank_value,
        "participant_count": rank.participant_count,
        "review_status": rank.review_status,
    }
