"""本地分析报告册发现/解析/登记（不访问网络，不调用 k12100）。"""

from __future__ import annotations

from datetime import date
from hashlib import sha256
from pathlib import Path
import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from . import private_files as files
from . import school_exam_pipeline as papers
from .school_exam_matcher import (
    build_canonical_exam_key,
    canonical_report_type_and_seq,
    normalize_academic_year,
    normalize_exam_date,
    normalize_grade,
    reports_represent_same_exam,
)
from .school_report_parser import parse_report_pdf


VALID_SCHOOL_SUBJECTS = ("chinese", "math", "english", "physics", "ethics")
SUBJECT_CN = {
    "chinese": "语文",
    "math": "数学",
    "english": "英语",
    "physics": "物理",
    "ethics": "道德与法治",
}
_STANDARD_TYPE_LABELS = {
    "monthly": "月考",
    "midterm": "期中",
    "final": "期末",
    "unified_practice": "统一练习",
}


def serialize_report(report: m.SchoolExamReport) -> dict[str, Any]:
    return {
        "id": report.id,
        "sha256": report.sha256,
        "filename": report.filename,
        "media_type": report.media_type,
        "byte_size": report.byte_size,
        "source_ref": report.source_ref,
        "title": report.title,
        "academic_year": report.academic_year,
        "grade": report.grade,
        "exam_type": report.exam_type,
        "exam_sequence": report.exam_sequence,
        "report_time": report.report_time,
        "external_exam_id": report.external_exam_id,
        "exam_date": report.exam_date,
        "report_total_score": report.report_total_score,
        "report_total_max": report.report_total_max,
        "total_class_rank": report.total_class_rank,
        "total_grade_rank": report.total_grade_rank,
        "total_participants": report.total_participants,
        "total_class_highest": report.total_class_highest,
        "total_grade_highest": report.total_grade_highest,
        "listed_subject_score": report.listed_subject_score,
        "listed_subject_max": report.listed_subject_max,
        "scope_status": report.scope_status,
        "pages": report.pages,
        "confidence": report.confidence,
        "status": report.status,
        "match_state": report.match_state,
        "linked_exam_ids": report.linked_exam_ids or [],
        "subjects": report.subjects or [],
        "questions": report.questions or [],
        "answer_card_pages": report.answer_card_pages or {},
        "warnings": report.warnings or [],
        "error_code": report.error_code,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "updated_at": report.updated_at.isoformat() if report.updated_at else None,
    }


def _parse_k12100_exam_date(raw: Any) -> tuple[str | None, date | None]:
    """按 k12100 实际日期格式解析：兼容完整日 YYYY-MM-DD 与年月 YYYY-MM（锚定 1 日入 Date 列）。"""
    normalized = normalize_exam_date(raw)
    if normalized is None:
        return None, None
    if len(normalized) == 10:
        try:
            return normalized, date.fromisoformat(normalized)
        except ValueError:
            return None, None
    if len(normalized) == 7:
        try:
            year, month = int(normalized[:4]), int(normalized[5:7])
            return normalized, date(year, month, 1)
        except ValueError:
            return None, None
    return None, None


def _extract_exam_type_from_text(text: str | None) -> tuple[str | None, int | None]:
    raw = str(text or "").strip()
    if not raw:
        return None, None
    match = re.search(r"(统一练习\s*[一二三四五六七八九十0-9]*|期中考试|期末考试|期中|期末|月考|阶段检测|模拟考试)", raw)
    if not match:
        return None, None
    token = re.sub(r"\s+", "", match.group(1))
    seq = None
    if token.startswith("统一练习"):
        suffix = token.removeprefix("统一练习")
        seq = {"一": 1, "1": 1, "二": 2, "2": 2, "三": 3, "3": 3}.get(suffix)
    return token, seq


def normalize_report_exam_type(
    raw_type: str | None,
    *,
    fallback_title: str | None = None,
    platform_type_name: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    """返回 (canonical_type, canonical_type_label, raw_display_label)。"""
    raw = str(raw_type or "").strip()
    if not raw and fallback_title:
        inferred, _ = _extract_exam_type_from_text(fallback_title)
        raw = inferred or ""
    if not raw and platform_type_name:
        raw = str(platform_type_name).strip()
    if not raw:
        return None, None, None

    if raw.startswith("统一练习") or raw == "unified_practice":
        return "unified_practice", _STANDARD_TYPE_LABELS["unified_practice"], raw
    if raw.startswith("期中") or raw == "midterm":
        return "midterm", _STANDARD_TYPE_LABELS["midterm"], raw
    if raw.startswith("期末") or raw == "final":
        return "final", _STANDARD_TYPE_LABELS["final"], raw
    if raw.startswith("月考") or raw.startswith("月度") or raw == "monthly":
        return "monthly", _STANDARD_TYPE_LABELS["monthly"], raw
    return "other", raw[:40], raw


def _clean_report_series_title(raw_title: str | None, fallback_label: str | None = None) -> str:
    text = str(raw_title or "").strip()
    text = re.sub(r"\[已脱敏\]", "", text)
    text = re.sub(r"(?:分析报告册|分析报告)\s*$", "", text).strip(" ·-_")
    return (text or fallback_label or "校考")[:160]


def _safe_unlink_unused_blob(db: Session, storage_key: str | None) -> None:
    """仅当没有任何报告/附件再引用同一 storage_key 时删除私有 blob。"""
    if not storage_key:
        return
    in_use = any(
        db.execute(select(model.id).where(model.storage_key == storage_key).limit(1)).first() is not None
        for model in (
            m.SchoolExamReport,
            m.SchoolExamReportAttachment,
            m.SchoolExamPaper,
            m.SchoolPaperAttachment,
        )
    )
    if not in_use:
        try:
            files.blob_path(storage_key).unlink(missing_ok=True)
        except OSError:
            pass


def _merge_report_subjects(existing_subjects: list[dict[str, Any]] | None, incoming_subjects: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """无损合并同场报告两版解析结果，保留最完整的排名与最高分字段。"""
    merged: dict[str, dict[str, Any]] = {}
    for entry in existing_subjects or []:
        if isinstance(entry, dict) and entry.get("subject"):
            merged[str(entry["subject"])] = dict(entry)
    for entry in incoming_subjects or []:
        if not isinstance(entry, dict) or not entry.get("subject"):
            continue
        subj = str(entry["subject"])
        prev = merged.get(subj)
        if prev is None:
            merged[subj] = dict(entry)
            continue
        combined = dict(prev)
        for k, v in entry.items():
            if v is not None:
                combined[k] = v
        merged[subj] = combined
    return list(merged.values())


def _refresh_canonical_exam_key(report: m.SchoolExamReport) -> str | None:
    ckey = build_canonical_exam_key(
        academic_year=report.academic_year,
        grade=report.grade,
        exam_type=report.exam_type,
        exam_sequence=report.exam_sequence,
        title=report.title,
        exam_date=report.exam_date,
    )
    if ckey:
        report.canonical_exam_key = ckey
    return ckey


def _find_canonical_report(
    db: Session,
    *,
    owner: str,
    ext_id: str | None,
    academic_year: str | None,
    grade: str | None,
    exam_type: str | None,
    exam_sequence: int | None,
    title: str | None,
    exam_date: str | None,
) -> m.SchoolExamReport | None:
    if ext_id:
        by_ext = db.execute(
            select(m.SchoolExamReport).where(
                m.SchoolExamReport.learner_id == owner,
                m.SchoolExamReport.external_exam_id == ext_id,
            )
        ).scalars().first()
        if by_ext is not None:
            return by_ext
    ckey = build_canonical_exam_key(
        academic_year=academic_year,
        grade=grade,
        exam_type=exam_type,
        exam_sequence=exam_sequence,
        title=title,
        exam_date=exam_date,
    )
    if ckey:
        by_ckey = db.execute(
            select(m.SchoolExamReport).where(
                m.SchoolExamReport.learner_id == owner,
                m.SchoolExamReport.canonical_exam_key == ckey,
            )
        ).scalars().first()
        if by_ckey is not None:
            return by_ckey
    candidates = db.execute(
        select(m.SchoolExamReport)
        .where(m.SchoolExamReport.learner_id == owner)
        .order_by(m.SchoolExamReport.created_at.desc(), m.SchoolExamReport.id.desc())
    ).scalars().all()
    for cand in candidates:
        if reports_represent_same_exam(
            a_ext_id=ext_id,
            a_year=academic_year,
            a_grade=grade,
            a_type=exam_type,
            a_seq=exam_sequence,
            a_title=title,
            a_date=exam_date,
            b=cand,
        ):
            return cand
    return None


def _apply_doc_fields_to_report(
    report: m.SchoolExamReport,
    *,
    doc: Any,
    resolved_title: str | None,
    resolved_year: str | None,
    resolved_grade: str | None,
    resolved_type: str | None,
    resolved_seq: int | None,
    ext_id: str | None,
    norm_date_str: str | None,
) -> None:
    keep_existing_authority = bool(
        (report.external_exam_id or str(report.source_ref or "").startswith("k12100/"))
        and not ext_id
    )
    if resolved_title and len(resolved_title) <= 200 and not keep_existing_authority:
        if not report.title or len(doc.subjects) >= len(report.subjects or []):
            report.title = resolved_title[:200]
    elif resolved_title and not report.title:
        report.title = resolved_title[:200]
    if resolved_year and not report.academic_year:
        report.academic_year = resolved_year
    norm_grade = normalize_grade(resolved_grade)
    if norm_grade and (not report.grade or not keep_existing_authority):
        report.grade = norm_grade
    if resolved_type and not report.exam_type:
        report.exam_type = resolved_type[:40]
    if resolved_seq is not None and report.exam_sequence is None:
        report.exam_sequence = resolved_seq
    if doc.identity.report_time:
        report.report_time = doc.identity.report_time
    if ext_id and not report.external_exam_id:
        report.external_exam_id = ext_id
    if norm_date_str and not report.exam_date:
        report.exam_date = norm_date_str
    if doc.report_total_score is not None:
        report.report_total_score = doc.report_total_score
    if doc.report_total_max is not None:
        report.report_total_max = doc.report_total_max
    if doc.total_class_rank is not None:
        report.total_class_rank = doc.total_class_rank
    if doc.total_grade_rank is not None:
        report.total_grade_rank = doc.total_grade_rank
    if doc.total_participants is not None:
        report.total_participants = doc.total_participants
    if getattr(doc, "total_class_highest", None) is not None:
        report.total_class_highest = doc.total_class_highest
    if getattr(doc, "total_grade_highest", None) is not None:
        report.total_grade_highest = doc.total_grade_highest
    if doc.listed_subject_score is not None:
        report.listed_subject_score = doc.listed_subject_score
    if doc.listed_subject_max is not None:
        report.listed_subject_max = doc.listed_subject_max
    report.scope_status = doc.scope_status
    report.subjects = _merge_report_subjects(report.subjects, [item.__dict__ for item in doc.subjects])
    if len(doc.questions) >= len(report.questions or []):
        report.questions = [item.__dict__ for item in doc.questions]
    if len(doc.answer_card_pages or {}) >= len(report.answer_card_pages or {}):
        report.answer_card_pages = doc.answer_card_pages
    report.pages = max(report.pages or 0, doc.pages)
    report.confidence = doc.confidence
    report.payload = doc.as_dict()
    report.warnings = doc.warnings
    _refresh_canonical_exam_key(report)


def register_report_bytes(
    db: Session,
    *,
    owner: str,
    data: bytes,
    filename: str,
    media_type: str = "application/pdf",
    source_ref: str,
    platform_meta: dict[str, Any] | None = None,
) -> tuple[m.SchoolExamReport, bool]:
    """解析并单场唯一登记分析报告册 PDF（按 sha256、external_exam_id 与规范身份去重合并）。"""
    meta = platform_meta or {}
    ext_id = str(meta.get("external_exam_id") or "").strip()[:80] or None
    norm_date_str, _ = _parse_k12100_exam_date(meta.get("exam_date"))
    meta_grade = normalize_grade(meta.get("grade"))
    meta_year = normalize_academic_year(meta.get("academic_year"))
    meta_name = str(meta.get("exam_name") or "").strip() or None
    meta_type_raw = str(meta.get("exam_type") or "").strip() or None

    digest = sha256(data).hexdigest()
    existing = db.execute(
        select(m.SchoolExamReport).where(
            m.SchoolExamReport.learner_id == owner,
            m.SchoolExamReport.sha256 == digest,
        )
    ).scalars().first()
    if existing is not None:
        changed = False
        if ext_id and not existing.external_exam_id:
            existing.external_exam_id = ext_id
            changed = True
        if norm_date_str and not existing.exam_date:
            existing.exam_date = norm_date_str
            changed = True
        if meta_grade and not existing.grade:
            existing.grade = meta_grade
            changed = True
        if meta_year and not existing.academic_year:
            existing.academic_year = meta_year
            changed = True
        if not existing.exam_type and (meta_name or meta_type_raw):
            inferred_type, inferred_seq = _extract_exam_type_from_text(meta_name or meta_type_raw)
            if inferred_type:
                existing.exam_type = inferred_type[:40]
                if existing.exam_sequence is None and inferred_seq is not None:
                    existing.exam_sequence = inferred_seq
                changed = True
        if changed:
            _refresh_canonical_exam_key(existing)
            match_report(db, report=existing)
        return existing, False

    doc = parse_report_pdf(data, filename=filename, digest=digest)
    if doc.kind != "exam_analysis_report":
        raise ValueError("NOT_EXAM_ANALYSIS_REPORT")

    resolved_year = doc.identity.academic_year or meta_year
    resolved_grade = normalize_grade(doc.identity.grade) or meta_grade
    inferred_type, inferred_seq = _extract_exam_type_from_text(meta_name or doc.identity.title or meta_type_raw)
    resolved_type = doc.identity.exam_type or inferred_type or (meta_type_raw[:40] if meta_type_raw else None)
    resolved_seq = doc.identity.exam_sequence if doc.identity.exam_sequence is not None else inferred_seq
    resolved_title = doc.identity.title or meta_name

    canonical = _find_canonical_report(
        db,
        owner=owner,
        ext_id=ext_id,
        academic_year=resolved_year,
        grade=resolved_grade,
        exam_type=resolved_type,
        exam_sequence=resolved_seq,
        title=resolved_title,
        exam_date=norm_date_str,
    )
    if canonical is not None:
        old_richness = (len(canonical.subjects or []), len(canonical.questions or []), canonical.pages or 0)
        new_richness = (len(doc.subjects), len(doc.questions), doc.pages)
        _apply_doc_fields_to_report(
            canonical,
            doc=doc,
            resolved_title=resolved_title,
            resolved_year=resolved_year,
            resolved_grade=resolved_grade,
            resolved_type=resolved_type,
            resolved_seq=resolved_seq,
            ext_id=ext_id,
            norm_date_str=norm_date_str,
        )
        if (ext_id or not canonical.external_exam_id) and new_richness >= old_richness:
            old_key = canonical.storage_key
            old_cards = db.execute(
                select(m.SchoolExamReportAttachment).where(m.SchoolExamReportAttachment.report_id == canonical.id)
            ).scalars().all()
            old_card_keys = [c.storage_key for c in old_cards]
            for card in old_cards:
                db.delete(card)
            canonical.sha256 = digest
            canonical.filename = papers._safe_paper_filename(filename)  # noqa: SLF001
            canonical.media_type = media_type
            canonical.byte_size = len(data)
            canonical.storage_key = files.write_blob(data)
            if source_ref.startswith("k12100/") or not str(canonical.source_ref or "").startswith("k12100/"):
                canonical.source_ref = source_ref[:255]
            db.flush()
            _safe_unlink_unused_blob(db, old_key)
            for ck in old_card_keys:
                _safe_unlink_unused_blob(db, ck)
        else:
            db.flush()
        match_report(db, report=canonical)
        return canonical, False

    storage_key = files.write_blob(data)
    report = m.SchoolExamReport(
        learner_id=owner,
        sha256=digest,
        filename=papers._safe_paper_filename(filename),  # noqa: SLF001
        media_type=media_type,
        byte_size=len(data),
        storage_key=storage_key,
        source_ref=source_ref[:255],
        title=resolved_title[:200] if resolved_title else None,
        academic_year=resolved_year,
        grade=resolved_grade,
        exam_type=resolved_type[:40] if resolved_type else None,
        exam_sequence=resolved_seq,
        report_time=doc.identity.report_time,
        external_exam_id=ext_id,
        canonical_exam_key=build_canonical_exam_key(
            academic_year=resolved_year,
            grade=resolved_grade,
            exam_type=resolved_type,
            exam_sequence=resolved_seq,
            title=resolved_title,
            exam_date=norm_date_str,
        ),
        exam_date=norm_date_str,
        report_total_score=doc.report_total_score,
        report_total_max=doc.report_total_max,
        total_class_rank=doc.total_class_rank,
        total_grade_rank=doc.total_grade_rank,
        total_participants=doc.total_participants,
        total_class_highest=getattr(doc, "total_class_highest", None),
        total_grade_highest=getattr(doc, "total_grade_highest", None),
        listed_subject_score=doc.listed_subject_score,
        listed_subject_max=doc.listed_subject_max,
        scope_status=doc.scope_status,
        pages=doc.pages,
        confidence=doc.confidence,
        status="needs_review",
        match_state="NEEDS_REVIEW",
        linked_exam_ids=[],
        subjects=[item.__dict__ for item in doc.subjects],
        questions=[item.__dict__ for item in doc.questions],
        answer_card_pages=doc.answer_card_pages,
        payload=doc.as_dict(),
        warnings=doc.warnings,
    )
    db.add(report)
    db.flush()
    match_report(db, report=report)
    return report, True


def scan_reports(db: Session, *, owner: str, environment: str | None = None) -> dict[str, Any]:
    inbox = papers.ensure_inbox(environment)
    found, _path_errors = papers.iter_source_files(inbox)
    reports: list[m.SchoolExamReport] = []
    skipped = 0
    for path in found:
        if path.suffix.lower() != ".pdf":
            continue
        try:
            data, media_type = papers._read_validated_file(path)  # noqa: SLF001
        except Exception:
            skipped += 1
            continue
        try:
            report, _created = register_report_bytes(
                db,
                owner=owner,
                data=data,
                filename=path.name,
                media_type=media_type,
                source_ref=f"inbox/{path.relative_to(inbox).as_posix()}",
            )
        except Exception:
            skipped += 1
            continue
        reports.append(report)
    db.commit()
    consolidate_duplicate_reports(db, owner=owner)
    canonical_reports: list[m.SchoolExamReport] = []
    seen_ids: set[str] = set()
    for item in papers.select_canonical_reports(reports):
        refreshed = db.get(m.SchoolExamReport, item.id)
        if refreshed is not None and refreshed.id not in seen_ids:
            seen_ids.add(refreshed.id)
            canonical_reports.append(refreshed)
    return {"discovered": len(canonical_reports), "skipped": skipped, "reports": [serialize_report(item) for item in canonical_reports]}


_REPORT_TYPE = {
    "期中考试": "midterm",
    "期中": "midterm",
    "期末考试": "final",
    "期末": "final",
    "月考": "monthly",
    "统一练习": "unified_practice",
}
_TYPE_ALIASES = {
    "midterm": {"midterm", "期中", "期中考试"},
    "final": {"final", "期末", "期末考试"},
    "monthly": {"monthly", "月考"},
    "unified_practice": {"unified_practice", "统一练习"},
}
_SEQUENCE_WORDS = {1: ("一", "1"), 2: ("二", "2"), 3: ("三", "3")}


def _normal_report_type(report: m.SchoolExamReport) -> str | None:
    value = (report.exam_type or "").strip()
    for prefix, code in _REPORT_TYPE.items():
        if value.startswith(prefix):
            return code
    return value or None


def _exam_matches_identity(report: m.SchoolExamReport, exam: m.SchoolExam) -> bool:
    if report.external_exam_id and exam.external_exam_id:
        return report.external_exam_id == exam.external_exam_id
    if report.academic_year and exam.academic_year and report.academic_year != exam.academic_year:
        return False
    rep_grade = normalize_grade(report.grade)
    ex_grade = normalize_grade(exam.grade)
    if rep_grade and ex_grade and rep_grade != ex_grade:
        return False
    report_date_str, _ = _parse_k12100_exam_date(report.exam_date)
    if report_date_str and exam.exam_date:
        exam_date_str = str(exam.exam_date)
        if report_date_str[:7] != exam_date_str[:7]:
            return False
        if len(report_date_str) == 10 and exam.source_kind == "k12100" and exam.exam_date.day != 1 and report_date_str != exam_date_str:
            return False
    report_type = _normal_report_type(report)
    haystack = " ".join(filter(None, (exam.title, exam.series_title)))
    if report_type:
        if exam.exam_type and exam.exam_type not in _TYPE_ALIASES.get(report_type, {report_type}):
            return False
        if not exam.exam_type:
            type_words = {
                "midterm": "期中",
                "final": "期末",
                "monthly": "月考",
                "unified_practice": "统一练习",
            }.get(report_type, report_type)
            if type_words not in haystack:
                return False
    if report.exam_sequence is not None and report_type == "unified_practice":
        patterns = {1: r"统一练习\s*(?:一|1)", 2: r"统一练习\s*(?:二|2)", 3: r"统一练习\s*(?:三|3)"}
        if report.exam_sequence in patterns and not re.search(patterns[report.exam_sequence], haystack):
            return False
    return True


def _exam_matches_subject(report: m.SchoolExamReport, exam: m.SchoolExam, subject: str) -> bool:
    return exam.subject == subject and _exam_matches_identity(report, exam)


def match_report(db: Session, *, report: m.SchoolExamReport) -> dict[str, Any]:
    """按学年度/年级/类型/序号/学科唯一关联；不做日期邻域兜底，不覆盖历史。"""
    subjects = report.subjects or []
    linked: list[dict[str, Any]] = []
    unresolved: list[str] = []
    ambiguous: list[str] = []
    for item in subjects:
        subject = str(item.get("subject") or "")
        if not subject:
            continue
        candidates = db.execute(
            select(m.SchoolExam).where(m.SchoolExam.learner_id == report.learner_id, m.SchoolExam.subject == subject)
        ).scalars().all()
        matches = [exam for exam in candidates if _exam_matches_subject(report, exam, subject)]
        if len(matches) == 1:
            exam = matches[0]
            linked.append(
                {
                    "subject": subject,
                    "exam_id": exam.id,
                    "title": exam.title,
                    "exam_date": str(exam.exam_date),
                    "match": "EXACT_MATCH",
                }
            )
        elif len(matches) > 1:
            ambiguous.append(subject)
        else:
            unresolved.append(subject)
    # 同场次其他学科：报告没有成绩行但同场已有校考档案时，仍建立场次关联。
    report_subjects = {str(item.get("subject") or "") for item in subjects}
    extra_by_subject: dict[str, list[m.SchoolExam]] = {}
    for exam in db.execute(
        select(m.SchoolExam).where(m.SchoolExam.learner_id == report.learner_id)
    ).scalars().all():
        if exam.subject in report_subjects:
            continue
        if _exam_matches_identity(report, exam):
            extra_by_subject.setdefault(exam.subject, []).append(exam)
    for subject, candidates in sorted(extra_by_subject.items()):
        if len(candidates) == 1:
            exam = candidates[0]
            linked.append(
                {
                    "subject": subject,
                    "exam_id": exam.id,
                    "title": exam.title,
                    "exam_date": str(exam.exam_date),
                    "match": "SESSION_ONLY",
                }
            )
    report.linked_exam_ids = linked
    if subjects and not unresolved and not ambiguous:
        report.match_state = "EXACT_MATCH"
    elif ambiguous:
        report.match_state = "AMBIGUOUS"
    elif not linked:
        report.match_state = "NOT_FOUND"
    elif subjects:
        # 缺卷是正常业务：已关联的学科全部唯一即可人工确认，缺卷学科保留待补。
        report.match_state = "PARTIAL_MATCH"
    else:
        report.match_state = "NEEDS_REVIEW"
    report.status = "needs_review" if report.match_state not in {"EXACT_MATCH", "PARTIAL_MATCH"} else "matched"
    report.updated_at = m.now()
    return {
        "linked_exam_ids": linked,
        "unresolved_subjects": unresolved,
        "ambiguous_subjects": ambiguous,
        "match_state": report.match_state,
    }


def build_answer_card_attachments(db: Session, *, report: m.SchoolExamReport, rotation: int = 0) -> dict[str, Any]:
    """把报告册中的答题卡页渲染为私有 PNG；按 (报告, 学科, 页码) 幂等。"""
    pages = report.answer_card_pages or {}
    if not pages:
        raise HTTPException(409, detail="REPORT_ANSWER_CARD_PAGES_MISSING")
    if rotation not in {0, 90, 180, 270}:
        raise HTTPException(422, detail="INVALID_ANSWER_CARD_ROTATION")
    try:
        source = files.blob_path(report.storage_key).read_bytes()
    except FileNotFoundError as exc:
        raise HTTPException(409, detail="REPORT_FILE_MISSING") from exc
    import subprocess
    from hashlib import sha256
    from tempfile import TemporaryDirectory

    active_pairs = {
        (str(subject), int(page_number))
        for subject, page_numbers in pages.items()
        for page_number in (page_numbers or [])
    }
    stale_cards = [
        att
        for att in db.execute(
            select(m.SchoolExamReportAttachment).where(m.SchoolExamReportAttachment.report_id == report.id)
        ).scalars().all()
        if (att.subject, att.page_number) not in active_pairs
    ]
    stale_keys = [att.storage_key for att in stale_cards]
    for att in stale_cards:
        db.delete(att)
    if stale_cards:
        db.flush()
        for key in stale_keys:
            _safe_unlink_unused_blob(db, key)

    with TemporaryDirectory(prefix="pageboy-card-") as directory:
        root = Path(directory)
        pdf = root / "report.pdf"
        pdf.write_bytes(source)
        created: list[m.SchoolExamReportAttachment] = []
        for subject, page_numbers in pages.items():
            for page_number in page_numbers:
                existing = db.execute(
                    select(m.SchoolExamReportAttachment).where(
                        m.SchoolExamReportAttachment.report_id == report.id,
                        m.SchoolExamReportAttachment.subject == subject,
                        m.SchoolExamReportAttachment.page_number == page_number,
                    )
                ).scalars().first()
                if existing is not None:
                    if existing.rotation != rotation:
                        existing.rotation = rotation
                    created.append(existing)
                    continue
                prefix = root / f"page-{subject}-{page_number}"
                result = subprocess.run(
                    ["pdftoppm", "-f", str(page_number), "-l", str(page_number), "-r", "120", "-png", str(pdf), str(prefix)],
                    capture_output=True,
                    timeout=60,
                    check=False,
                )
                images = sorted(root.glob(f"{prefix.name}-*.png"))
                if result.returncode != 0 or not images:
                    continue
                data = images[0].read_bytes()
                attachment = m.SchoolExamReportAttachment(
                    report_id=report.id,
                    learner_id=report.learner_id,
                    subject=subject,
                    page_number=page_number,
                    filename=f"答题卡-{subject}-{page_number}.png",
                    media_type="image/png",
                    byte_size=len(data),
                    storage_key=files.write_blob(data),
                    sha256=sha256(data).hexdigest(),
                    rotation=rotation,
                )
                db.add(attachment)
                db.flush()
                created.append(attachment)
        db.commit()
        for attachment in created:
            db.refresh(attachment)
        synced = sync_answer_cards_to_ledger(db, report=report)
        db.commit()
        return {"created": len(created), "attachments": [_serialize_card(attachment) for attachment in created], "ledger_synced": synced}


def _serialize_card(attachment: m.SchoolExamReportAttachment) -> dict[str, Any]:
    return {
        "id": attachment.id,
        "subject": attachment.subject,
        "page_number": attachment.page_number,
        "filename": attachment.filename,
        "media_type": attachment.media_type,
        "byte_size": attachment.byte_size,
        "rotation": attachment.rotation,
        "created_at": attachment.created_at.isoformat() if attachment.created_at else None,
    }


def list_answer_card_attachments(db: Session, *, report: m.SchoolExamReport) -> list[dict[str, Any]]:
    rows = db.execute(
        select(m.SchoolExamReportAttachment)
        .where(m.SchoolExamReportAttachment.report_id == report.id)
        .order_by(m.SchoolExamReportAttachment.subject, m.SchoolExamReportAttachment.page_number)
    ).scalars().all()
    return [_serialize_card(item) for item in rows]


def sync_report_ranks_and_benchmarks(
    db: Session,
    *,
    report: m.SchoolExamReport,
    ownership_basis: str = "k12100_total_report_pdf",
) -> int:
    """将报告中的学科级与全科总分排名及班级/年级最高分幂等写入台账与排名快照。"""
    links = [link for link in (report.linked_exam_ids or []) if isinstance(link, dict) and link.get("exam_id")]
    if not links:
        return 0
    subject_map = {
        str(item.get("subject")): item
        for item in (report.subjects or [])
        if isinstance(item, dict) and item.get("subject")
    }

    total_entries: list[dict[str, Any]] = []
    if report.total_class_rank is not None and int(report.total_class_rank) > 0:
        total_entries.append(
            {
                "scope": "class",
                "rank_value": int(report.total_class_rank),
                "participant_count": None,
                "percentile": None,
                "highest_score": report.total_class_highest,
                "source_field": "report.total.class_rank",
            }
        )
    if report.total_grade_rank is not None and int(report.total_grade_rank) > 0:
        total_entries.append(
            {
                "scope": "grade",
                "rank_value": int(report.total_grade_rank),
                "participant_count": int(report.total_participants) if report.total_participants else None,
                "percentile": None,
                "highest_score": report.total_grade_highest,
                "source_field": "report.total.grade_rank",
            }
        )

    created_total = 0
    for link in links:
        subject = str(link.get("subject") or "")
        exam = db.get(m.SchoolExam, str(link.get("exam_id") or ""))
        if exam is None or exam.learner_id != report.learner_id:
            continue
        item = subject_map.get(subject)
        subj_entries: list[dict[str, Any]] = []
        if item is not None:
            cls_hi = item.get("class_highest")
            grd_hi = item.get("grade_highest")
            if cls_hi is not None and (exam.class_highest is None or not exam.confirmed_by_user):
                exam.class_highest = round(float(cls_hi), 2)
            if grd_hi is not None and (exam.grade_highest is None or not exam.confirmed_by_user):
                exam.grade_highest = round(float(grd_hi), 2)
            if item.get("class_rank") is not None and int(item["class_rank"]) > 0:
                subj_entries.append(
                    {
                        "scope": "class",
                        "rank_value": int(item["class_rank"]),
                        "participant_count": None,
                        "percentile": None,
                        "highest_score": cls_hi,
                        "source_field": f"report.{subject}.class_rank",
                    }
                )
            if item.get("grade_rank") is not None and int(item["grade_rank"]) > 0:
                participants = int(item["participants"]) if item.get("participants") else None
                subj_entries.append(
                    {
                        "scope": "grade",
                        "rank_value": int(item["grade_rank"]),
                        "participant_count": participants,
                        "percentile": None,
                        "highest_score": grd_hi,
                        "source_field": f"report.{subject}.grade_rank",
                    }
                )
        if subj_entries:
            created_total += len(
                papers.persist_rank_entries(
                    db,
                    exam=exam,
                    owner=report.learner_id,
                    subject_scope=subject,
                    entries=subj_entries,
                    source_name="k12100",
                    ownership_status="verified",
                    ownership_basis=ownership_basis,
                )
            )
        if total_entries:
            created_total += len(
                papers.persist_rank_entries(
                    db,
                    exam=exam,
                    owner=report.learner_id,
                    subject_scope="total",
                    entries=total_entries,
                    source_name="k12100",
                    ownership_status="verified",
                    ownership_basis=ownership_basis,
                )
            )
    return created_total


def apply_report_to_ledger(
    db: Session,
    *,
    report: m.SchoolExamReport,
    confirm_subjects: set[str] | None = None,
) -> dict[str, Any]:
    """把已人工确认报告中的待核对分值与排名基准回写台账；绝不连带自动锁定未逐科核对的总分。"""
    subject_map = {str(item.get("subject")): item for item in (report.subjects or [])}
    applied: list[str] = []
    conflicts: list[str] = []
    skipped: list[str] = []
    for link in report.linked_exam_ids or []:
        subject = str(link.get("subject") or "")
        values = subject_map.get(subject)
        if values is None:
            skipped.append(subject)
            continue
        exam = db.get(m.SchoolExam, link.get("exam_id"))
        if exam is None or exam.learner_id != report.learner_id:
            continue
        score = values.get("score")
        max_score = values.get("max_score")
        if score is None or max_score is None:
            skipped.append(subject)
            continue
        if exam.confirmed_by_user:
            if abs(float(exam.earned_points) - float(score)) > 0.01 or abs(float(exam.max_points) - float(max_score)) > 0.01:
                conflicts.append(subject)
            continue
        exam.earned_points = float(score)
        exam.max_points = float(max_score)
        if confirm_subjects is not None and subject in confirm_subjects:
            exam.confirmed_by_user = True
        if not exam.grade and report.grade:
            exam.grade = report.grade
        if not exam.exam_type and report.exam_type:
            canonical_type, canonical_label, _ = normalize_report_exam_type(report.exam_type, fallback_title=report.title)
            if canonical_type:
                exam.exam_type = canonical_type
                if not exam.exam_type_label and canonical_label:
                    exam.exam_type_label = canonical_label
        if not exam.academic_year and report.academic_year:
            exam.academic_year = report.academic_year
        if not exam.external_exam_id and report.external_exam_id:
            exam.external_exam_id = report.external_exam_id
        applied.append(subject)
    ranks_synced = sync_report_ranks_and_benchmarks(db, report=report, ownership_basis="matched_report_pdf")
    return {"applied_subjects": applied, "conflict_subjects": conflicts, "skipped_subjects": skipped, "ranks_synced": ranks_synced}


def upsert_exams_from_report(
    db: Session,
    *,
    report: m.SchoolExamReport,
    platform_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """按下载报告与平台元数据新建、更新未锁分或补全空身份字段；绝不静默覆盖锁分或身份冲突。"""
    meta = platform_meta or {}
    norm_date_str, canonical_date = _parse_k12100_exam_date(report.exam_date or meta.get("exam_date"))
    norm_year = normalize_academic_year(report.academic_year or meta.get("academic_year"))
    norm_grade = normalize_grade(report.grade) or normalize_grade(meta.get("grade"))
    canonical_type, canonical_type_label, raw_type_display = normalize_report_exam_type(
        report.exam_type,
        fallback_title=report.title or meta.get("exam_name"),
        platform_type_name=meta.get("exam_type"),
    )
    series_title = _clean_report_series_title(report.title or meta.get("exam_name"), fallback_label=raw_type_display)
    ext_id = report.external_exam_id or (str(meta.get("external_exam_id") or "").strip()[:80] or None)

    actions: list[dict[str, Any]] = []
    counts = {
        "created": 0,
        "updated": 0,
        "filled": 0,
        "unchanged": 0,
        "locked_conflict": 0,
        "identity_conflict": 0,
        "awaiting_exam_date": 0,
        "ambiguous": 0,
        "skipped": 0,
    }

    for item in report.subjects or []:
        subject = str(item.get("subject") or "").strip()
        if subject not in VALID_SCHOOL_SUBJECTS:
            continue
        subject_cn = SUBJECT_CN[subject]
        score = item.get("score")
        max_score = item.get("max_score")
        candidates = db.execute(
            select(m.SchoolExam).where(m.SchoolExam.learner_id == report.learner_id, m.SchoolExam.subject == subject)
        ).scalars().all()
        if ext_id:
            ext_matches = [exam for exam in candidates if exam.external_exam_id == ext_id]
            matches = ext_matches if ext_matches else [exam for exam in candidates if _exam_matches_subject(report, exam, subject)]
        else:
            matches = [exam for exam in candidates if _exam_matches_subject(report, exam, subject)]

        if not matches and canonical_date is not None and norm_date_str is not None:
            # 单学生同一天同一学年同类型同科若已有冲突档案（如年级误录），阻断并发建重并提示冲突。
            near_conflicts = [
                exam
                for exam in candidates
                if (not exam.external_exam_id or not ext_id or exam.external_exam_id == ext_id)
                and (not norm_year or not exam.academic_year or exam.academic_year == norm_year)
                and (not canonical_type or not exam.exam_type or exam.exam_type == canonical_type)
                and exam.exam_date is not None
                and (
                    (len(norm_date_str) == 10 and exam.exam_date == canonical_date)
                    or (exam.source_kind == "manual" and exam.exam_date.day == 1 and str(exam.exam_date)[:7] == norm_date_str[:7])
                )
            ]
            if near_conflicts:
                matches = near_conflicts

        if len(matches) > 1:
            counts["ambiguous"] += 1
            actions.append(
                {
                    "subject": subject,
                    "subject_label": subject_cn,
                    "action": "ambiguous",
                    "exam_id": "",
                    "exam_title": "",
                    "exam_date": norm_date_str or "",
                    "earned_points": score,
                    "max_points": max_score,
                    "confirmed_by_user": False,
                    "filled_fields": [],
                    "conflict_fields": [],
                    "message": f"库中存在 {len(matches)} 个同科候选档案，已跳过自动写入。",
                }
            )
            continue

        if len(matches) == 0:
            if canonical_date is None or norm_date_str is None:
                counts["awaiting_exam_date"] += 1
                actions.append(
                    {
                        "subject": subject,
                        "subject_label": subject_cn,
                        "action": "awaiting_exam_date",
                        "exam_id": "",
                        "exam_title": "",
                        "exam_date": "",
                        "earned_points": score,
                        "max_points": max_score,
                        "confirmed_by_user": False,
                        "filled_fields": [],
                        "conflict_fields": [],
                        "message": "k12100 未提供可验证考试日期，未自动建档；可手工建档后重试。",
                    }
                )
                continue
            if score is None or max_score is None or float(max_score) <= 0:
                counts["skipped"] += 1
                actions.append(
                    {
                        "subject": subject,
                        "subject_label": subject_cn,
                        "action": "skipped",
                        "exam_id": "",
                        "exam_title": "",
                        "exam_date": norm_date_str,
                        "earned_points": score,
                        "max_points": max_score,
                        "confirmed_by_user": False,
                        "filled_fields": [],
                        "conflict_fields": [],
                        "message": "报告缺少该科总分或满分，跳过新建。",
                    }
                )
                continue
            new_score = round(float(score), 2)
            new_max = round(float(max_score), 2)
            if new_score > new_max:
                counts["skipped"] += 1
                actions.append(
                    {
                        "subject": subject,
                        "subject_label": subject_cn,
                        "action": "skipped",
                        "exam_id": "",
                        "exam_title": "",
                        "exam_date": norm_date_str,
                        "earned_points": score,
                        "max_points": max_score,
                        "confirmed_by_user": False,
                        "filled_fields": [],
                        "conflict_fields": [],
                        "message": "报告得分高于满分，已拦截建档，请核对报告解析。",
                    }
                )
                continue
            desired_title = f"{series_title} · {subject_cn}"[:160]
            exam = m.SchoolExam(
                learner_id=report.learner_id,
                subject=subject,
                exam_date=canonical_date,
                title=desired_title,
                earned_points=new_score,
                max_points=new_max,
                confirmed_by_user=False,
                grade=norm_grade,
                exam_type=canonical_type,
                exam_type_label=canonical_type_label,
                academic_year=norm_year,
                series_title=series_title[:160],
                external_exam_id=ext_id,
                source_kind="k12100",
            )
            db.add(exam)
            db.flush()
            counts["created"] += 1
            actions.append(
                {
                    "subject": subject,
                    "subject_label": subject_cn,
                    "action": "created",
                    "exam_id": exam.id,
                    "exam_title": exam.title,
                    "exam_date": str(exam.exam_date),
                    "earned_points": exam.earned_points,
                    "max_points": exam.max_points,
                    "confirmed_by_user": False,
                    "filled_fields": [
                        field
                        for field, val in (
                            ("exam_date", norm_date_str),
                            ("academic_year", norm_year),
                            ("grade", norm_grade),
                            ("exam_type", canonical_type),
                            ("external_exam_id", ext_id),
                        )
                        if val
                    ],
                    "conflict_fields": [],
                    "message": "已按 k12100 首页日期与报告身份新建待核对档案。",
                }
            )
            continue

        exam = matches[0]
        conflicts: list[str] = []
        if exam.academic_year and norm_year and exam.academic_year != norm_year:
            conflicts.append("academic_year")
        if exam.grade and norm_grade and normalize_grade(exam.grade) != norm_grade:
            conflicts.append("grade")
        if exam.exam_type and canonical_type:
            if exam.exam_type != canonical_type:
                conflicts.append("exam_type")
            elif exam.exam_type == "other" and exam.exam_type_label and canonical_type_label and exam.exam_type_label != canonical_type_label:
                conflicts.append("exam_type")
        if canonical_date is not None and norm_date_str is not None and exam.exam_date is not None:
            exam_date_str = str(exam.exam_date)
            if exam_date_str[:7] != norm_date_str[:7]:
                conflicts.append("exam_date")
            elif len(norm_date_str) == 10 and exam.exam_date.day != 1 and exam.exam_date != canonical_date:
                conflicts.append("exam_date")
        if exam.external_exam_id and ext_id and exam.external_exam_id != ext_id:
            conflicts.append("external_exam_id")

        if conflicts:
            counts["identity_conflict"] += 1
            actions.append(
                {
                    "subject": subject,
                    "subject_label": subject_cn,
                    "action": "identity_conflict",
                    "exam_id": exam.id,
                    "exam_title": exam.title,
                    "exam_date": str(exam.exam_date),
                    "earned_points": exam.earned_points,
                    "max_points": exam.max_points,
                    "confirmed_by_user": bool(exam.confirmed_by_user),
                    "filled_fields": [],
                    "conflict_fields": conflicts,
                    "message": f"与库中非空身份字段冲突（{'、'.join(conflicts)}），未覆盖原档案。",
                }
            )
            continue

        filled_fields: list[str] = []
        if not exam.grade and norm_grade:
            exam.grade = norm_grade[:20]
            filled_fields.append("grade")
        elif exam.grade and norm_grade and normalize_grade(exam.grade) == norm_grade and exam.grade != norm_grade:
            exam.grade = norm_grade[:20]
        if not exam.exam_type and canonical_type:
            exam.exam_type = canonical_type
            filled_fields.append("exam_type")
        if not exam.exam_type_label and canonical_type_label:
            exam.exam_type_label = canonical_type_label[:40]
            filled_fields.append("exam_type_label")
        if not exam.academic_year and norm_year:
            exam.academic_year = norm_year
            filled_fields.append("academic_year")
        if not exam.series_title and series_title:
            exam.series_title = series_title[:160]
            filled_fields.append("series_title")
        if not exam.external_exam_id and ext_id:
            exam.external_exam_id = ext_id
            filled_fields.append("external_exam_id")
        if (
            canonical_date is not None
            and norm_date_str is not None
            and len(norm_date_str) == 10
            and exam.source_kind == "manual"
            and exam.exam_date is not None
            and exam.exam_date.day == 1
            and exam.exam_date.year == canonical_date.year
            and exam.exam_date.month == canonical_date.month
            and exam.exam_date != canonical_date
        ):
            exam.exam_date = canonical_date
            filled_fields.append("exam_date")

        score_changed = False
        locked_conflict = False
        if score is not None and max_score is not None and float(max_score) > 0:
            new_score = round(float(score), 2)
            new_max = round(float(max_score), 2)
            if exam.confirmed_by_user:
                if abs(float(exam.earned_points) - new_score) > 0.01 or abs(float(exam.max_points) - new_max) > 0.01:
                    locked_conflict = True
            elif new_score <= new_max and (
                abs(float(exam.earned_points) - new_score) > 0.01 or abs(float(exam.max_points) - new_max) > 0.01
            ):
                exam.max_points = new_max
                exam.earned_points = new_score
                score_changed = True

        if locked_conflict:
            action = "locked_conflict"
            msg = (
                f"已人工锁定总分 {exam.earned_points:g}/{exam.max_points:g}，与报告 {float(score):g}/{float(max_score):g} 不同；"
                "按锁分红线保留原值。"
            )
        elif score_changed:
            action = "updated"
            msg = "已更新待核对总分" + (f"并补全 {'、'.join(filled_fields)}" if filled_fields else "") + "。"
        elif filled_fields:
            action = "filled"
            msg = f"已补全缺失字段（{'、'.join(filled_fields)}）。"
        else:
            action = "unchanged"
            msg = "档案已完整，无需改动。"

        counts[action] += 1
        actions.append(
            {
                "subject": subject,
                "subject_label": subject_cn,
                "action": action,
                "exam_id": exam.id,
                "exam_title": exam.title,
                "exam_date": str(exam.exam_date),
                "earned_points": exam.earned_points,
                "max_points": exam.max_points,
                "confirmed_by_user": bool(exam.confirmed_by_user),
                "filled_fields": filled_fields,
                "conflict_fields": [],
                "message": msg,
            }
        )

    db.flush()
    match_report(db, report=report)
    ranks_synced = sync_report_ranks_and_benchmarks(
        db,
        report=report,
        ownership_basis="k12100_total_report_pdf" if (ext_id or report.external_exam_id) else "matched_report_pdf",
    )
    return {"counts": counts, "actions": actions, "ranks_synced": ranks_synced}


def sync_answer_cards_to_ledger(db: Session, *, report: m.SchoolExamReport) -> int:
    """把报告答题卡页同步为已关联校考的私有附件；按 SHA-256 与规范页码集合去重，避免重复写入。"""
    links = {str(link.get("subject")): str(link.get("exam_id")) for link in (report.linked_exam_ids or [])}
    if not links:
        return 0
    from hashlib import sha256
    from io import BytesIO
    from PIL import Image

    synced = 0
    active_pages = {
        (str(subj), int(p))
        for subj, plist in (report.answer_card_pages or {}).items()
        for p in (plist or [])
    }
    attachments = [
        card
        for card in db.execute(
            select(m.SchoolExamReportAttachment)
            .where(m.SchoolExamReportAttachment.report_id == report.id)
            .order_by(m.SchoolExamReportAttachment.subject, m.SchoolExamReportAttachment.page_number)
        ).scalars().all()
        if not active_pages or (card.subject, card.page_number) in active_pages
    ]
    by_subj_cards: dict[str, list[m.SchoolExamReportAttachment]] = {}
    for card in attachments:
        by_subj_cards.setdefault(card.subject, []).append(card)

    for subject, cards in by_subj_cards.items():
        exam_id = links.get(subject)
        if not exam_id:
            continue
        expected_names = {f"报告答题卡-{c.subject}-第{c.page_number}页.png" for c in cards}
        existing_rows = db.execute(
            select(m.SchoolPaperAttachment)
            .where(m.SchoolPaperAttachment.school_exam_id == exam_id)
            .order_by(m.SchoolPaperAttachment.created_at.asc(), m.SchoolPaperAttachment.id.asc())
        ).scalars().all()
        # 清理旧版同一科目的孤立/重复报告答题卡（如早年 21 页或跨科错配页号残余）
        kept_hashes: set[str] = set()
        for att in list(existing_rows):
            is_auto = att.filename.startswith(f"报告答题卡-{subject}-第")
            is_stale = is_auto and att.filename not in expected_names
            is_dup_auto = is_auto and att.sha256 in kept_hashes
            if is_stale or is_dup_auto:
                old_key = att.storage_key
                db.delete(att)
                db.flush()
                _safe_unlink_unused_blob(db, old_key)
                existing_rows.remove(att)
            else:
                kept_hashes.add(att.sha256)

        by_name = {att.filename: att for att in existing_rows}
        known_hashes = {att.sha256 for att in existing_rows}

        for card in cards:
            filename = f"报告答题卡-{card.subject}-第{card.page_number}页.png"
            try:
                data = files.blob_path(card.storage_key).read_bytes()
            except FileNotFoundError:
                continue
            if card.rotation:
                try:
                    with Image.open(BytesIO(data)) as image:
                        output = BytesIO()
                        image.convert("RGB").rotate(-int(card.rotation), expand=True).save(output, format="PNG")
                        data = output.getvalue()
                except Exception:
                    continue
            digest = sha256(data).hexdigest()
            exists = by_name.get(filename)
            if exists is not None:
                if exists.sha256 != digest:
                    old_key = exists.storage_key
                    exists.storage_key = files.write_blob(data)
                    exists.sha256 = digest
                    exists.byte_size = len(data)
                    known_hashes.add(digest)
                    db.flush()
                    _safe_unlink_unused_blob(db, old_key)
                continue
            if digest in known_hashes:
                continue
            new_att = m.SchoolPaperAttachment(
                school_exam_id=exam_id,
                owner_id=report.learner_id,
                filename=filename,
                media_type="image/png",
                sha256=digest,
                byte_size=len(data),
                storage_key=files.write_blob(data),
            )
            db.add(new_att)
            known_hashes.add(digest)
            by_name[filename] = new_att
            synced += 1
    return synced


def consolidate_duplicate_reports(db: Session, *, owner: str) -> int:
    """无损合并历史重复写入的同场报告（如收件箱 21 页版与 k12100 25 页版），并清理重复附件。"""
    reports = db.execute(
        select(m.SchoolExamReport)
        .where(m.SchoolExamReport.learner_id == owner)
        .order_by(m.SchoolExamReport.created_at.desc(), m.SchoolExamReport.id.desc())
    ).scalars().all()
    if len(reports) <= 1:
        return 0

    clusters: list[list[m.SchoolExamReport]] = []
    for rep in reports:
        rep_links = [
            str(link.get("exam_id") or "")
            for link in (rep.linked_exam_ids or [])
            if isinstance(link, dict) and link.get("exam_id")
        ]
        placed = False
        for grp in clusters:
            anchor = grp[0]
            if reports_represent_same_exam(
                a_ext_id=rep.external_exam_id,
                a_year=rep.academic_year,
                a_grade=rep.grade,
                a_type=rep.exam_type,
                a_seq=rep.exam_sequence,
                a_title=rep.title,
                a_date=rep.exam_date,
                a_linked_ids=rep_links,
                b=anchor,
            ):
                grp.append(rep)
                placed = True
                break
        if not placed:
            clusters.append([rep])

    removed = 0
    for grp in clusters:
        if len(grp) <= 1:
            continue
        grp.sort(
            key=lambda r: (
                bool(r.external_exam_id),
                len(r.subjects or []),
                len(r.questions or []),
                r.pages or 0,
                bool(r.exam_date),
            ),
            reverse=True,
        )
        winner = grp[0]
        for loser in grp[1:]:
            if not winner.external_exam_id and loser.external_exam_id:
                winner.external_exam_id = loser.external_exam_id
            if not winner.exam_date and loser.exam_date:
                winner.exam_date = loser.exam_date
            if winner.total_participants is None and loser.total_participants is not None:
                winner.total_participants = loser.total_participants
            if winner.total_class_highest is None and loser.total_class_highest is not None:
                winner.total_class_highest = loser.total_class_highest
            if winner.total_grade_highest is None and loser.total_grade_highest is not None:
                winner.total_grade_highest = loser.total_grade_highest
            winner.subjects = _merge_report_subjects(loser.subjects, winner.subjects)
            if len(loser.questions or []) > len(winner.questions or []):
                winner.questions = loser.questions
            if len(loser.answer_card_pages or {}) > len(winner.answer_card_pages or {}):
                winner.answer_card_pages = loser.answer_card_pages
            if loser.status == "confirmed" and winner.status != "confirmed":
                winner.status = "confirmed"

            loser_key = loser.storage_key
            loser_cards = db.execute(
                select(m.SchoolExamReportAttachment).where(m.SchoolExamReportAttachment.report_id == loser.id)
            ).scalars().all()
            loser_card_keys = [c.storage_key for c in loser_cards]
            for card in loser_cards:
                db.delete(card)
            db.delete(loser)
            db.flush()
            _safe_unlink_unused_blob(db, loser_key)
            for ck in loser_card_keys:
                _safe_unlink_unused_blob(db, ck)
            removed += 1
        if winner.grade:
            norm_w_grade = normalize_grade(winner.grade)
            if norm_w_grade:
                winner.grade = norm_w_grade
        _refresh_canonical_exam_key(winner)
        match_report(db, report=winner)
        sync_answer_cards_to_ledger(db, report=winner)
    if removed:
        db.commit()
    return removed


def hydrate_incomplete_local_reports(
    db: Session,
    *,
    owner: str,
    auto_map_fn: Any = None,
) -> dict[str, Any]:
    """无需联网 k12100：合并重复报告、从本地已存 PDF 补全缺失最高分/排名/草稿/答题卡。"""
    deduped = consolidate_duplicate_reports(db, owner=owner)
    reports = db.execute(
        select(m.SchoolExamReport).where(m.SchoolExamReport.learner_id == owner)
    ).scalars().all()

    reparsed = 0
    ranks_synced = 0
    cards_synced = 0
    drafts_created = 0
    for report in reports:
        needs_reparse = (
            report.total_class_highest is None
            or report.total_grade_highest is None
            or any(
                isinstance(s, dict) and (s.get("grade_highest") is None or s.get("class_highest") is None)
                for s in (report.subjects or [])
            )
        )
        if needs_reparse and report.storage_key:
            blob = files.blob_path(report.storage_key)
            if blob.is_file() and not blob.is_symlink():
                try:
                    doc = parse_report_pdf(blob.read_bytes(), filename=report.filename, digest=report.sha256)
                    if doc.kind == "exam_analysis_report":
                        _apply_doc_fields_to_report(
                            report,
                            doc=doc,
                            resolved_title=doc.identity.title or report.title,
                            resolved_year=doc.identity.academic_year or report.academic_year,
                            resolved_grade=normalize_grade(doc.identity.grade) or normalize_grade(report.grade),
                            resolved_type=doc.identity.exam_type or report.exam_type,
                            resolved_seq=doc.identity.exam_sequence if doc.identity.exam_sequence is not None else report.exam_sequence,
                            ext_id=report.external_exam_id,
                            norm_date_str=report.exam_date,
                        )
                        reparsed += 1
                except Exception:
                    pass

        if report.exam_date:
            upsert = upsert_exams_from_report(db, report=report, platform_meta={})
            ranks_synced += int(upsert.get("ranks_synced") or 0)
        else:
            match_report(db, report=report)
            ranks_synced += sync_report_ranks_and_benchmarks(
                db,
                report=report,
                ownership_basis="k12100_total_report_pdf" if report.external_exam_id else "matched_report_pdf",
            )
        db.commit()
        db.refresh(report)

        drafts = generate_item_drafts(db, report=report, update_unconfirmed_drafts=True)
        drafts_created += int(drafts.get("created") or 0)
        if auto_map_fn:
            if auto_map_fn(db, report):
                db.commit()
        _refresh_canonical_exam_key(report)
        if report.answer_card_pages:
            try:
                cards = build_answer_card_attachments(db, report=report, rotation=0)
                cards_synced += int(cards.get("ledger_synced") or 0)
            except HTTPException:
                pass
        db.commit()

    return {
        "deduped_reports": deduped,
        "reparsed_reports": reparsed,
        "ranks_synced": ranks_synced,
        "cards_synced": cards_synced,
        "drafts_created": drafts_created,
    }


def collect_complete_skip_targets(db: Session, *, owner: str) -> dict[str, Any]:
    """核对库中所有已同步场次完整性，生成下载前跳过列表与完整身份列表。"""
    synced = papers._serialize_synced_reports(db, owner=owner)  # noqa: SLF001
    complete_ext_ids: set[str] = set()
    complete_identities: list[dict[str, Any]] = []
    incomplete_reports: list[dict[str, Any]] = []
    for rep in synced:
        comp = rep.get("completeness") or {}
        if not comp.get("complete"):
            incomplete_reports.append(
                {
                    "id": rep["id"],
                    "title": rep.get("title"),
                    "external_exam_id": rep.get("external_exam_id"),
                    "missing": comp.get("missing") or [],
                }
            )
            continue
        if rep.get("external_exam_id"):
            complete_ext_ids.add(str(rep["external_exam_id"]).strip())
        ctype, seq = canonical_report_type_and_seq(rep.get("exam_type"), None, rep.get("title"))
        grade = normalize_grade(rep.get("grade"))
        year = normalize_academic_year(rep.get("academic_year"))
        if year and grade and ctype:
            complete_identities.append(
                {
                    "report_id": rep["id"],
                    "academic_year": year,
                    "grade": grade,
                    "exam_type": ctype,
                    "exam_sequence": seq,
                    "exam_date_ym": str(rep.get("exam_date") or "")[:7] or None,
                }
            )
    return {
        "synced_reports": synced,
        "complete_external_exam_ids": sorted(complete_ext_ids),
        "complete_identities": complete_identities,
        "incomplete_reports": incomplete_reports,
        "all_complete": bool(synced) and len(incomplete_reports) == 0,
    }


def generate_item_drafts(
    db: Session,
    *,
    report: m.SchoolExamReport,
    update_unconfirmed_drafts: bool = False,
) -> dict[str, Any]:
    """把报告逐题表转成台账 ocr_draft；知识点留待人工映射，不确认、不进画像。"""
    links = {str(link.get("subject")): str(link.get("exam_id")) for link in (report.linked_exam_ids or [])}
    created = 0
    updated = 0
    skipped = 0
    unmapped_subjects: list[str] = []
    for question in report.questions or []:
        subject = str(question.get("subject") or "")
        exam_id = links.get(subject)
        if not exam_id:
            if subject not in unmapped_subjects:
                unmapped_subjects.append(subject)
            skipped += 1
            continue
        label = str(question.get("number") or "").strip()[:160]
        if not label:
            skipped += 1
            continue
        max_score = question.get("max_score")
        score = question.get("score")
        exists = db.execute(
            select(m.SchoolExamItem).where(
                m.SchoolExamItem.school_exam_id == exam_id,
                m.SchoolExamItem.question_label == label,
            )
        ).scalars().first()
        if exists is not None:
            if (
                update_unconfirmed_drafts
                and not exists.confirmed_by_user
                and exists.scoring_origin == "ocr_draft"
                and max_score is not None
                and score is not None
            ):
                new_earned = float(score)
                new_max = float(max_score)
                if new_earned <= new_max and (
                    abs(float(exists.earned_points) - new_earned) > 0.01
                    or abs(float(exists.max_points) - new_max) > 0.01
                ):
                    exists.earned_points = new_earned
                    exists.max_points = new_max
                    exists.draft_confidence = str(question.get("confidence") or exists.draft_confidence or "medium")
                    exists.draft_reason = f"分析报告册第{question.get('page')}页；题型={question.get('question_type') or '未知'}"
                    updated += 1
                    continue
            skipped += 1
            continue
        if max_score is None:
            skipped += 1
            continue
        db.add(
            m.SchoolExamItem(
                school_exam_id=exam_id,
                question_label=label,
                knowledge_id="unmapped",
                earned_points=float(score or 0),
                max_points=float(max_score),
                scoring_origin="ocr_draft",
                confirmed_by_user=False,
                draft_confidence=str(question.get("confidence") or "medium"),
                draft_reason=f"分析报告册第{question.get('page')}页；题型={question.get('question_type') or '未知'}",
            )
        )
        created += 1
    db.commit()
    return {"created": created, "updated": updated, "skipped": skipped, "unmapped_subjects": unmapped_subjects}


def ai_map_report_items(db: Session, *, report: m.SchoolExamReport) -> dict[str, Any]:
    """用 DeepSeek 文本模型把题干映射到已发布知识点；只发题干+编码清单，只写候选。"""
    from .school_paper_parser import (
        VisionParserConfigError,
        VisionParserUnavailableError,
        _post_deepseek_json,
        load_vision_config,
        parse_paper_skeleton_from_text,
    )
    from .main import _resolve_school_knowledge_meta
    import json as _json
    import re as _re

    try:
        cfg = load_vision_config(require_key=True)
    except VisionParserConfigError as exc:
        raise HTTPException(503, detail="DEEPSEEK_NOT_CONFIGURED") from exc
    if cfg is None:
        raise HTTPException(503, detail="DEEPSEEK_NOT_CONFIGURED")
    links = {str(link.get("subject")): str(link.get("exam_id")) for link in (report.linked_exam_ids or [])}
    mapped = 0
    failures: list[str] = []
    for subject, exam_id in links.items():
        has_taxonomy, nodes, _names, _aliases = _resolve_school_knowledge_meta(db, subject, set())
        if not has_taxonomy or not nodes:
            continue
        attachments = db.execute(
            select(m.SchoolPaperAttachment).where(
                m.SchoolPaperAttachment.school_exam_id == exam_id,
                m.SchoolPaperAttachment.owner_id == report.learner_id,
            )
        ).scalars().all()
        original = next((a for a in attachments if "答题卡" not in a.filename), None)
        if original is None:
            continue
        try:
            data = files.blob_path(original.storage_key).read_bytes()
            text, _version = files.parse_text(data, original.media_type)
        except Exception:
            failures.append(subject)
            continue
        skeleton = parse_paper_skeleton_from_text(text, subject, nodes)
        by_number = {}
        for item in skeleton:
            match = _re.search(r"(\d+)", str(item.get("question_label") or ""))
            if match and item.get("stem"):
                by_number[match.group(1)] = item
        rows = db.execute(select(m.SchoolExamItem).where(m.SchoolExamItem.school_exam_id == exam_id)).scalars().all()
        pending = []
        for row in rows:
            if row.confirmed_by_user or row.knowledge_id != "unmapped":
                continue
            match = _re.search(r"(\d+)", row.question_label)
            stem = by_number.get(match.group(1), {}).get("stem") if match else None
            if stem:
                pending.append({"question": row.question_label, "stem": stem})
        if not pending:
            continue
        catalog = "\n".join(f"- {n['code']} : {n.get('name') or n['code']}" for n in nodes[:120])
        prompt = (
            "你是校考知识点标注器。只能从下面知识点编码中选择；无法确定填 null。"
            "不得编造编码。只返回 JSON：{\"mappings\":[{\"question\":\"题号\",\"knowledge_id\":\"编码或null\"}]}。\n"
            f"知识点编码：\n{catalog}\n\n题目：\n" + _json.dumps(pending, ensure_ascii=False)
        )
        try:
            result = _post_deepseek_json(
                cfg,
                model=cfg.text_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
            )
        except VisionParserUnavailableError:
            failures.append(subject)
            continue
        mappings = result.get("mappings") if isinstance(result, dict) else None
        if not isinstance(mappings, list):
            failures.append(subject)
            continue
        valid = {str(n["code"]): str(n.get("name") or n["code"]) for n in nodes if n.get("code")}
        for entry in mappings:
            if not isinstance(entry, dict):
                continue
            code = str(entry.get("knowledge_id") or "").strip()
            question = str(entry.get("question") or "").strip()
            if code not in valid or not question:
                continue
            row = next((item for item in rows if item.question_label == question and not item.confirmed_by_user), None)
            if row is None:
                continue
            row.knowledge_id = code
            row.draft_confidence = "ai_matched"
            row.draft_knowledge_candidates = [{"knowledge_id": code, "title": valid[code], "reason": "DeepSeek 基于题干语义与知识点库匹配"}]
            row.draft_reason = (row.draft_reason or "") + "；知识点由 DeepSeek 文本匹配，待人工确认"
            mapped += 1
    db.commit()
    return {"mapped": mapped, "failed_subjects": failures}
