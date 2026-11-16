"""本地分析报告册发现/解析/登记（不访问网络，不调用 k12100）。"""

from __future__ import annotations

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
from .school_report_parser import parse_report_pdf


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
        "report_total_score": report.report_total_score,
        "report_total_max": report.report_total_max,
        "total_class_rank": report.total_class_rank,
        "total_grade_rank": report.total_grade_rank,
        "total_participants": report.total_participants,
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
        digest = sha256(data).hexdigest()
        existing = db.execute(
            select(m.SchoolExamReport).where(
                m.SchoolExamReport.learner_id == owner,
                m.SchoolExamReport.sha256 == digest,
            )
        ).scalars().first()
        if existing is not None:
            reports.append(existing)
            continue
        try:
            doc = parse_report_pdf(data, filename=path.name, digest=digest)
        except Exception:
            skipped += 1
            continue
        if doc.kind != "exam_analysis_report":
            skipped += 1
            continue
        storage_key = files.write_blob(data)
        report = m.SchoolExamReport(
            learner_id=owner,
            sha256=digest,
            filename=papers._safe_paper_filename(path.name),  # noqa: SLF001
            media_type=media_type,
            byte_size=len(data),
            storage_key=storage_key,
            source_ref=f"inbox/{path.relative_to(inbox).as_posix()}"[:255],
            title=doc.identity.title,
            academic_year=doc.identity.academic_year,
            grade=doc.identity.grade,
            exam_type=doc.identity.exam_type,
            exam_sequence=doc.identity.exam_sequence,
            report_time=doc.identity.report_time,
            report_total_score=doc.report_total_score,
            report_total_max=doc.report_total_max,
            total_class_rank=doc.total_class_rank,
            total_grade_rank=doc.total_grade_rank,
            total_participants=doc.total_participants,
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
        reports.append(report)
    db.commit()
    for report in reports:
        db.refresh(report)
    return {"discovered": len(reports), "skipped": skipped, "reports": [serialize_report(item) for item in reports]}


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


def _grade_key(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    return {"初三": "9", "九年级": "9", "初二": "8", "八年级": "8", "初一": "7", "七年级": "7"}.get(text, text)


def _exam_matches_identity(report: m.SchoolExamReport, exam: m.SchoolExam) -> bool:
    if report.academic_year and exam.academic_year and report.academic_year != exam.academic_year:
        return False
    if report.grade and exam.grade and _grade_key(report.grade) != _grade_key(exam.grade):
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


def apply_report_to_ledger(db: Session, *, report: m.SchoolExamReport) -> dict[str, Any]:
    """把已人工确认的报告学科成绩回写到已关联校考；不覆盖已确认冲突。"""
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
        exam.confirmed_by_user = True
        if not exam.grade and report.grade:
            exam.grade = report.grade
        if not exam.exam_type and report.exam_type:
            exam.exam_type = "unified_practice" if report.exam_type.startswith("统一练习") else {
                "期中考试": "midterm", "期末考试": "final", "月考": "monthly"
            }.get(report.exam_type, exam.exam_type)
        if not exam.academic_year and report.academic_year:
            exam.academic_year = report.academic_year
        applied.append(subject)
    return {"applied_subjects": applied, "conflict_subjects": conflicts, "skipped_subjects": skipped}


def sync_answer_cards_to_ledger(db: Session, *, report: m.SchoolExamReport) -> int:
    """把报告答题卡页同步为已关联校考的私有附件；幂等，按文件名去重。"""
    links = {str(link.get("subject")): str(link.get("exam_id")) for link in (report.linked_exam_ids or [])}
    if not links:
        return 0
    from hashlib import sha256
    from io import BytesIO
    from PIL import Image

    synced = 0
    attachments = db.execute(
        select(m.SchoolExamReportAttachment).where(m.SchoolExamReportAttachment.report_id == report.id)
    ).scalars().all()
    for card in attachments:
        exam_id = links.get(card.subject)
        if not exam_id:
            continue
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
        exists = db.execute(
            select(m.SchoolPaperAttachment).where(
                m.SchoolPaperAttachment.school_exam_id == exam_id,
                m.SchoolPaperAttachment.filename == filename,
            )
        ).scalars().first()
        if exists is not None:
            if exists.sha256 != digest:
                old_key = exists.storage_key
                exists.storage_key = files.write_blob(data)
                exists.sha256 = digest
                exists.byte_size = len(data)
                try:
                    files.blob_path(old_key).unlink(missing_ok=True)
                except Exception:
                    pass
            continue
        db.add(
            m.SchoolPaperAttachment(
                school_exam_id=exam_id,
                owner_id=report.learner_id,
                filename=filename,
                media_type="image/png",
                sha256=sha256(data).hexdigest(),
                byte_size=len(data),
                storage_key=files.write_blob(data),
            )
        )
        synced += 1
    return synced


def generate_item_drafts(db: Session, *, report: m.SchoolExamReport) -> dict[str, Any]:
    """把报告逐题表转成台账 ocr_draft；知识点留待人工映射，不确认、不进画像。"""
    links = {str(link.get("subject")): str(link.get("exam_id")) for link in (report.linked_exam_ids or [])}
    created = 0
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
        exists = db.execute(
            select(m.SchoolExamItem).where(
                m.SchoolExamItem.school_exam_id == exam_id,
                m.SchoolExamItem.question_label == label,
            )
        ).scalars().first()
        if exists is not None:
            skipped += 1
            continue
        max_score = question.get("max_score")
        score = question.get("score")
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
    return {"created": created, "skipped": skipped, "unmapped_subjects": unmapped_subjects}


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
