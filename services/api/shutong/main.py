"""Private API foundation. Read CODEX_START_HERE.md before extending."""
from __future__ import annotations
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from fastapi import FastAPI, Depends, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import delete, or_, select, func, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from .auth import require_admin, require_student, require_owner
from .topic_labels import get_topic_label, get_student_advice, TAXONOMY_MAP, SYNTHETIC_MAP
from .taxonomy_bridge import resolve_question_to_candidate_codes
from .content import create_question_draft
from .ingestion import router as ingestion_router, require_import_integrity
from .fourcorpus import router as corpus_router
from .learning_api import router as learning_router, get_evidence, _load_effective_knowledge_nodes, _get_mapped_evidence, serialize_school_coach_session
from .research import official_reject_reason
from .database import get_db
from .home import HomeIdentityError, build_school_exam_archive_dir_name
from . import models as m
from . import private_files as files
from . import school_paper_parser as paper_parser
from . import k12100_backfill
from . import k12100_report_sync
from . import school_exam_pipeline as exam_pipeline
from . import school_report_pipeline as report_pipeline
from .schemas import SourceIn, QuestionIn, QuestionRevisionOut, AttemptIn, SelfAssessmentIn, SchoolExamIn, SchoolExamConfirmIn, SchoolExamItemsIn, SchoolExamItemAnalysisIn, AdminReturnReflectionIn, SchoolCoachSessionOut, SchoolItemStemExtractIn, SchoolItemStemExtractOut, SchoolItemStemPatchIn, SchoolExamStemsConfirmOut, SchoolExamErrorAnalysisOut, SchoolItemConfirmIn, SchoolItemConfirmBatchIn, SchoolExamParseDraftsIn, SchoolExamSyncDraftsIn, SchoolExamAutoAssociateIn, SchoolExamAutoAssociateOut, K12100SyncJobStartIn, K12100ImportBundleIn, K12100ReportJobStartIn, SchoolPaperScanIn, SchoolPaperMatchIn, SchoolPaperCollectIn, SchoolExamRankConfirmIn, SchoolExamReportConfirmIn, SchoolExamReportPatchIn, SchoolExamReportSubjectIn, GoalIn, Subject, SchoolExamSubject, SchoolExamArchiveSubject
from .guidance import Evidence, MODEL_VERSION, summarize, make_plan, compare_validation, pool_health, compute_knowledge_mastery, analyze_school_exam_errors, question_label_sort_key, MIN_DISTINCT_ITEMS

app = FastAPI(title="书童 ShuTong API", version="0.1.0", docs_url=None, redoc_url=None)
logger = logging.getLogger(__name__)
app.include_router(ingestion_router)
app.include_router(corpus_router)
app.include_router(learning_router)
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if x.strip()], allow_credentials=False, allow_methods=["GET","POST"], allow_headers=["Authorization", "Content-Type"])

@app.get("/health/live")
def live():
    # app_revision 供部署/回滚演练核对“哪个构建在服务”（ST-017）；未设置时如实报 dev。
    # env 标识运行环境（dev/test/prod），供脚本拒绝向 prod 写入演示数据；未设置即 dev。
    return {"status": "alive", "app_revision": os.getenv("SHUTONG_APP_REVISION", "dev"), "env": os.getenv("SHUTONG_ENV", "dev")}

@app.get("/health/ready")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(503, detail="database unavailable")
    return {"status": "ready"}

@app.get("/api/admin/verify")
def verify_admin(owner: str = Depends(require_admin)):
    return {"status": "ok", "role": "admin"}

@app.get("/api/student/verify")
def verify_student(student: str = Depends(require_student)):
    return {"status": "ok", "role": "student"}

@app.post("/api/admin/sources", status_code=201)
def add_source(payload: SourceIn, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    if payload.source_class == "official_exam":
        reason = official_reject_reason(payload.title)
        if reason:
            raise HTTPException(422, detail=reason)
    # 仅格式合法的哈希不能证明原件存在；来源哈希由附件上传端计算并登记。
    if payload.sha256 is not None:
        raise HTTPException(422, detail="SOURCE_HASH_REQUIRES_ATTACHMENT_UPLOAD")
    src = m.SourceDocument(**payload.model_dump())
    db.add(src); db.commit(); db.refresh(src)
    return {"id": src.id, "status": "recorded"}

@app.post("/api/admin/questions", status_code=201)
def add_question(payload: QuestionIn, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    src = db.get(m.SourceDocument, payload.source_document_id)
    if src is None:
        raise HTTPException(404, detail="source not found")
    if payload.media_attachment_id is not None:
        attachment = db.get(m.SourceAttachment, payload.media_attachment_id)
        if attachment is None or attachment.source_document_id != payload.source_document_id or attachment.owner_id != owner:
            raise HTTPException(422, detail="MEDIA_ATTACHMENT_INVALID")
    v = create_question_draft(db, src, payload)
    db.commit(); db.refresh(v)
    return {"id": v.id, "question_id": v.question_id, "status": v.status}

@app.post("/api/admin/questions/{version_id}/revisions", status_code=201, response_model=QuestionRevisionOut,
          responses={401: {"description": "Owner authorization required"}, 404: {"description": "Version not found"},
                     409: {"description": "Unpublished version, changed source, or revision number conflict"}})
def revise_question(version_id: str, payload: QuestionIn, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    """已发布题的更正只创建草稿，不继承原版审核状态。"""
    original = db.get(m.QuestionVersion, version_id)
    if original is None:
        raise HTTPException(404, detail="version not found")
    if original.status != "published":
        raise HTTPException(409, detail="only published versions can be revised")
    question = db.get(m.Question, original.question_id)
    if payload.source_document_id != question.source_document_id:
        raise HTTPException(409, detail="revision cannot change source")
    if payload.media_attachment_id is not None:
        # 修订创建新版本，媒体引用同样须"存在/同源/属 owner"（§1 创建即校验；Gate 整改补齐）。
        media = db.get(m.SourceAttachment, payload.media_attachment_id)
        if media is None or media.source_document_id != payload.source_document_id or media.owner_id != owner:
            raise HTTPException(422, detail="MEDIA_ATTACHMENT_INVALID")
    next_version = db.scalar(select(func.max(m.QuestionVersion.version)).where(m.QuestionVersion.question_id == question.id)) + 1
    revised = m.QuestionVersion(question_id=question.id, version=next_version, **payload.model_dump(exclude={"source_document_id"}))
    db.add(revised)
    try:
        db.flush()
        imported = db.get(m.ImportedQuestion, original.id)
        if imported is not None:
            db.add(m.ImportedQuestion(question_version_id=revised.id, attachment_id=imported.attachment_id))
        db.commit()
    except IntegrityError:
        # 版本唯一约束拦截并行修订的编号冲突，失败请求不留下部分记录。
        db.rollback()
        raise HTTPException(409, detail="QUESTION_REVISION_CONFLICT")
    db.refresh(revised)
    return {"id": revised.id, "question_id": revised.question_id, "version": revised.version, "status": revised.status}

@app.post("/api/admin/questions/{version_id}/review")
def review_question(version_id: str, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    v = db.get(m.QuestionVersion, version_id)
    if v is None:
        raise HTTPException(404, detail="version not found")
    if v.status != "draft":
        raise HTTPException(409, detail="only draft versions can be reviewed")
    v.reviewed_by_human = True; v.status = "reviewed"
    db.commit()
    return {"id": v.id, "status": "reviewed"}

@app.post("/api/admin/questions/{version_id}/publish")
def publish_question(version_id: str, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    v = db.get(m.QuestionVersion, version_id)
    if v is None:
        raise HTTPException(404, detail="version not found")
    src = db.get(m.SourceDocument, db.get(m.Question, v.question_id).source_document_id)
    if v.status != "reviewed" or not v.reviewed_by_human or src is None or not src.verified or src.rights_status not in {"licensed", "personal_use_reviewed"}:
        raise HTTPException(409, detail="QUESTION_NOT_APPROVED_FOR_PRIVATE_PUBLICATION")
    require_import_integrity(db, v)
    v.status = "published"; v.published_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": v.id, "status": "published"}

@app.get("/api/subjects")
def subjects(student: str = Depends(require_student)):
    return ["math", "chinese", "english", "physics"]

@app.get("/api/practice/next")
def next_item(subject: Subject, purpose: str = Query(default="training", pattern="^(training|evaluation)$"), knowledge_id: str | None = None, student: str = Depends(require_student), db: Session = Depends(get_db)):
    """A returned question is immediately recorded as exposed. Evaluation requires unseen item."""
    # P0-1 隔离整改：学生端取题接口禁止使用内部 knowledge_id 筛选参数，杜绝内部知识点代号反向探测
    if knowledge_id is not None:
        raise HTTPException(status_code=400, detail="KNOWLEDGE_FILTER_FORBIDDEN: 学生端接口禁止使用内部知识点参数筛选")
    owner = student
    # 按逻辑题选择最新已发布版，较新的草稿不替代当前发布版。
    latest = select(m.QuestionVersion.question_id, func.max(m.QuestionVersion.version).label("version")).where(m.QuestionVersion.status == "published").group_by(m.QuestionVersion.question_id).subquery()
    versions = db.execute(select(m.QuestionVersion).join(m.Question).join(latest, (m.QuestionVersion.question_id == latest.c.question_id) & (m.QuestionVersion.version == latest.c.version)).where(m.Question.subject == subject, m.QuestionVersion.status == "published").order_by(m.QuestionVersion.created_at, m.QuestionVersion.id)).scalars().all()
    candidates = list(versions)
    # 曝光计数按逻辑题批量聚合。此查询必须渲染出字面 token `GROUP BY exposures.question_id`——
    # test_practice_concurrency.py 的 is_exposure_read 钩子按它匹配以制造受控竞争窗，勿改写查询形状。
    counts = dict(db.execute(select(m.Exposure.question_id, func.count()).where(m.Exposure.learner_id == owner).group_by(m.Exposure.question_id)).all())
    if purpose == "training":
        # 复练合法：全部候选按（曝光次数升序, created_at, id）轮换，绝不跳过已见题。
        ordered = sorted(candidates, key=lambda v: (counts.get(v.question_id, 0), v.created_at, v.id))
    else:
        # evaluation 只认曝光次数==0 的逻辑题（含 training 已见）。
        ordered = [v for v in candidates if counts.get(v.question_id, 0) == 0]
    for v in ordered:
        seen = counts.get(v.question_id, 0) > 0
        exp = m.Exposure(learner_id=owner, question_id=v.question_id, question_version_id=v.id, purpose=purpose, is_unseen_at_exposure=not seen)
        db.add(exp)
        try:
            db.commit()
        except IntegrityError:
            # 并发抢曝被 uq_exposure_first_unseen 拦截。evaluation 失败者绝不给已见题落曝光，换下一候选，
            # 候选耗尽则落到 404；training 失败者重查 seen 后以复练身份重插（复练无唯一约束，合法）。
            db.rollback()
            if purpose == "evaluation":
                continue
            seen_now = db.execute(select(func.count()).select_from(m.Exposure).where(m.Exposure.learner_id == owner, m.Exposure.question_id == v.question_id)).scalar_one() > 0
            exp = m.Exposure(learner_id=owner, question_id=v.question_id, question_version_id=v.id, purpose=purpose, is_unseen_at_exposure=not seen_now)
            db.add(exp)
            db.commit()  # 复练曝光不受部分唯一索引约束；若仍失败则如实抛出，不吞错。
        db.refresh(exp)
        return {"exposure_id": exp.id, "question_version_id": v.id, "purpose": purpose, "unseen_at_exposure": exp.is_unseen_at_exposure, "stem": v.stem, "kind": v.kind, "group_context": v.group_context, "media_attachment_id": v.media_attachment_id, "options": v.options, "max_points": v.max_points, "subject": subject}
    raise HTTPException(404, detail="NO_ELIGIBLE_QUESTION")

@app.post("/api/practice/attempts", status_code=201)
def submit_attempt(payload: AttemptIn, student: str = Depends(require_student), db: Session = Depends(get_db)):
    owner = student
    def resolve_existing(existing):
        # 同幂等键复用：载荷（exposure_id/answer/hints_used）全同才承认已记录，返回已持久行的判定结果。
        if existing.exposure_id != payload.exposure_id or existing.answer != payload.answer or existing.hints_used != payload.hints_used:
            raise HTTPException(409, detail="IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD")
        return {"id": existing.id, "status": "already_recorded", "earned_points": existing.earned_points, "max_points": existing.max_points, "scoring_origin": existing.scoring_origin}
    existing = db.execute(select(m.AnswerAttempt).where(m.AnswerAttempt.learner_id == owner, m.AnswerAttempt.client_attempt_id == payload.client_attempt_id)).scalar_one_or_none()
    if existing:
        return resolve_existing(existing)
    exp = db.get(m.Exposure, payload.exposure_id)
    if exp is None or exp.learner_id != owner:
        raise HTTPException(404, detail="exposure not found")
    v = db.get(m.QuestionVersion, exp.question_version_id)
    # 客观判分：single_choice 精确比对；short_answer 归一化比对；subjective 不判分，自评走独立来源记录。
    if v.kind == "single_choice":
        earned = v.max_points if payload.answer.strip() == v.correct_answer.strip() else 0.0
        origin = "reviewed_answer_key"
    elif v.kind == "short_answer":
        normalize = lambda value: " ".join(value.split()).casefold()
        earned = v.max_points if normalize(payload.answer) == normalize(v.correct_answer) else 0.0
        origin = "reviewed_answer_key"
    else:
        earned = None
        origin = "ungraded_subjective"
    attempt = m.AnswerAttempt(learner_id=owner, client_attempt_id=payload.client_attempt_id, exposure_id=exp.id, question_version_id=v.id, answer=payload.answer, earned_points=earned, max_points=v.max_points, scoring_origin=origin, hints_used=payload.hints_used)
    db.add(attempt)
    try:
        db.commit()
    except IntegrityError:
        # 并发由提交点的唯一约束裁决（uq_attempt_idempotency / uq_attempt_exposure），天然竞争无 500：
        # 同键竞争失败者重查幂等键并按载荷比对返回；同曝光异键失败者重查曝光返回 409；都查不到则原样抛出。
        db.rollback()
        winner = db.execute(select(m.AnswerAttempt).where(m.AnswerAttempt.learner_id == owner, m.AnswerAttempt.client_attempt_id == payload.client_attempt_id)).scalar_one_or_none()
        if winner is not None:
            return resolve_existing(winner)
        clash = db.execute(select(m.AnswerAttempt.id).where(m.AnswerAttempt.exposure_id == exp.id).limit(1)).first()
        if clash is not None:
            raise HTTPException(409, detail="EXPOSURE_ALREADY_SUBMITTED")
        raise
    db.refresh(attempt)
    return {"id": attempt.id, "status": "recorded", "earned_points": earned, "max_points": v.max_points, "scoring_origin": origin, "evaluation_valid_unseen": exp.purpose == "evaluation" and exp.is_unseen_at_exposure and not payload.hints_used}

@app.get("/api/practice/attempts/{attempt_id}/reference")
def attempt_reference(attempt_id: str, student: str = Depends(require_student), db: Session = Depends(get_db)):
    """主观题参考答案：作答先行才可对答案（以 attempt 存在为门）；非主观不适用。"""
    owner = student
    attempt = db.get(m.AnswerAttempt, attempt_id)
    if attempt is None or attempt.learner_id != owner:
        raise HTTPException(404, detail="attempt not found")
    version = db.get(m.QuestionVersion, attempt.question_version_id)
    if version.kind != "subjective":
        raise HTTPException(409, detail="REFERENCE_NOT_APPLICABLE")
    return {"reference_answer": version.correct_answer, "max_points": version.max_points}

@app.post("/api/practice/attempts/{attempt_id}/self-assessment", status_code=201)
def record_self_assessment(attempt_id: str, payload: SelfAssessmentIn, student: str = Depends(require_student), db: Session = Depends(get_db)):
    """主观自评为独立来源记录：不改写作答行，一次自评不可更新（INV-04），不进客观证据。"""
    owner = student
    attempt = db.get(m.AnswerAttempt, attempt_id)
    if attempt is None or attempt.learner_id != owner:
        raise HTTPException(404, detail="attempt not found")
    version = db.get(m.QuestionVersion, attempt.question_version_id)
    if version.kind != "subjective":
        raise HTTPException(409, detail="SELF_ASSESSMENT_NOT_APPLICABLE")
    if payload.self_earned_points > attempt.max_points:
        raise HTTPException(422, detail="self_earned_points exceeds max_points")
    if db.scalar(select(m.SelfAssessment).where(m.SelfAssessment.attempt_id == attempt.id)) is not None:
        raise HTTPException(409, detail="SELF_ASSESSMENT_ALREADY_RECORDED")
    record = m.SelfAssessment(attempt_id=attempt.id, learner_id=owner, self_earned_points=payload.self_earned_points,
                              max_points=attempt.max_points, scoring_origin="self_assessment")
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        # 并发重复自评被 attempt 唯一索引拦截；按落库事实裁决返回 409，不产生未处理 500（Gate MINOR#1）。
        db.rollback()
        if db.scalar(select(m.SelfAssessment).where(m.SelfAssessment.attempt_id == attempt.id)) is not None:
            raise HTTPException(409, detail="SELF_ASSESSMENT_ALREADY_RECORDED")
        raise
    db.refresh(record)
    return {"id": record.id, "attempt_id": record.attempt_id, "self_earned_points": record.self_earned_points,
            "max_points": record.max_points, "scoring_origin": record.scoring_origin}

@app.get("/api/practice/attempts")
def list_attempts(subject: Subject, student: str = Depends(require_student), db: Session = Depends(get_db)):
    """评分来源溯源列表：作答行 origin 与自评记录并列可审计；自评不进 get_evidence/profile。"""
    owner = student
    rows = db.execute(select(m.AnswerAttempt, m.QuestionVersion, m.Exposure)
                      .join(m.QuestionVersion, m.QuestionVersion.id == m.AnswerAttempt.question_version_id)
                      .join(m.Question, m.Question.id == m.QuestionVersion.question_id)
                      .join(m.Exposure, m.Exposure.id == m.AnswerAttempt.exposure_id)
                      .where(m.AnswerAttempt.learner_id == owner, m.Question.subject == subject)
                      .order_by(m.AnswerAttempt.created_at.desc(), m.AnswerAttempt.id.desc())).all()
    assessments = {}
    if rows:
        records = db.scalars(select(m.SelfAssessment).where(m.SelfAssessment.attempt_id.in_([row[0].id for row in rows]))).all()
        assessments = {record.attempt_id: record for record in records}
    return [{"id": attempt.id, "question_version_id": attempt.question_version_id, "purpose": exposure.purpose,
             "kind": version.kind, "answer": attempt.answer, "earned_points": attempt.earned_points,
             "max_points": attempt.max_points, "scoring_origin": attempt.scoring_origin, "hints_used": attempt.hints_used,
             "self_assessment": ({"id": record.id, "self_earned_points": record.self_earned_points,
                                  "max_points": record.max_points, "scoring_origin": record.scoring_origin}
                                 if (record := assessments.get(attempt.id)) is not None else None),
             "created_at": attempt.created_at}
            for attempt, version, exposure in rows]

@app.post("/api/school-exams", status_code=201)
def add_school_exam(payload: SchoolExamIn, owner: str = Depends(require_admin), db: Session = Depends(get_db)):
    record = m.SchoolExam(learner_id=owner, **payload.model_dump())
    db.add(record)
    db.flush()
    record.archive_dir = build_school_exam_archive_dir_name(record.exam_date, record.title, record.id)
    files.ensure_school_exam_archive_dirs(record.archive_dir)
    db.commit()
    db.refresh(record)
    return {
        "id": record.id,
        "subject": record.subject,
        "status": "user_confirmed" if record.confirmed_by_user else "unconfirmed",
        "knowledge_evidence_created": False,
    }

@app.get("/api/school-exams")
def get_school_exams(
    subject: SchoolExamArchiveSubject = "all",
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    stmt = select(m.SchoolExam).where(m.SchoolExam.learner_id == owner)
    if subject != "all":
        stmt = stmt.where(m.SchoolExam.subject.in_([subject, "all"]))
    exams = db.execute(stmt.order_by(m.SchoolExam.exam_date.desc())).scalars().all()
    return [
        {
            "id": e.id,
            "subject": e.subject,
            "title": e.title,
            "exam_date": str(e.exam_date),
            "earned_points": e.earned_points,
            "max_points": e.max_points,
            "confirmed_by_user": e.confirmed_by_user,
            "school_name": e.school_name,
            "grade": e.grade,
            "exam_type": e.exam_type,
            "exam_type_label": e.exam_type_label,
            "academic_year": e.academic_year,
            "term": e.term,
            "series_title": e.series_title,
            "external_exam_id": e.external_exam_id,
            "source_kind": e.source_kind,
        }
        for e in exams
    ]

@app.post("/api/school-exams/{exam_id}/confirm")
def confirm_school_exam(exam_id: str, payload: SchoolExamConfirmIn, owner: str = Depends(require_admin), db: Session = Depends(get_db)):
    """待核对校考总分的人工补充与确认；确认后不可变，且永不产生考点证据（INV-05）。"""
    exam = db.get(m.SchoolExam, exam_id)
    if exam is None or exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")
    if payload.subject and exam.subject == "all":
        from sqlalchemy.orm.attributes import flag_modified

        reports = db.execute(
            select(m.SchoolExamReport).where(m.SchoolExamReport.learner_id == owner)
        ).scalars().all()
        target_report = None
        for rep in reports:
            if any(isinstance(lnk, dict) and lnk.get("exam_id") == exam.id for lnk in (rep.linked_exam_ids or [])):
                target_report = rep
                break
        if target_report is None:
            raise HTTPException(404, detail="linked report not found")
        updated_subjects = [dict(item) if isinstance(item, dict) else item for item in (target_report.subjects or [])]
        matched_entry = next(
            (item for item in updated_subjects if isinstance(item, dict) and item.get("subject") == payload.subject),
            None,
        )
        if matched_entry is None:
            raise HTTPException(404, detail="subject not found in linked report")
        if matched_entry.get("confirmed_by_user"):
            if payload.earned_points == matched_entry.get("score"):
                raise HTTPException(409, detail="SCHOOL_EXAM_ALREADY_CONFIRMED")
            raise HTTPException(409, detail="SCHOOL_EXAM_IMMUTABLE")
        subj_max = matched_entry.get("max_score")
        if subj_max is not None and payload.earned_points > float(subj_max):
            raise HTTPException(422, detail="earned_points exceeds max_points")
        matched_entry["score"] = payload.earned_points
        matched_entry["confirmed_by_user"] = True
        target_report.subjects = updated_subjects
        flag_modified(target_report, "subjects")
        all_confirmed = all(
            bool(item.get("confirmed_by_user"))
            for item in updated_subjects
            if isinstance(item, dict) and item.get("subject")
        )
        if all_confirmed and updated_subjects:
            exam.confirmed_by_user = True
            total_earned = sum(float(item.get("score") or 0) for item in updated_subjects if isinstance(item, dict))
            total_max = sum(float(item.get("max_score") or 0) for item in updated_subjects if isinstance(item, dict))
            if total_max > 0:
                exam.earned_points = round(total_earned, 2)
                exam.max_points = round(total_max, 2)
        db.commit()
        db.refresh(exam)
        return {
            "id": exam.id,
            "subject": payload.subject,
            "title": exam.title,
            "exam_date": str(exam.exam_date),
            "earned_points": payload.earned_points,
            "max_points": float(subj_max) if subj_max is not None else exam.max_points,
            "confirmed_by_user": True,
            "knowledge_evidence_created": False,
        }
    if exam.confirmed_by_user:
        if payload.earned_points == exam.earned_points:
            raise HTTPException(409, detail="SCHOOL_EXAM_ALREADY_CONFIRMED")
        raise HTTPException(409, detail="SCHOOL_EXAM_IMMUTABLE")
    if payload.earned_points > exam.max_points:
        raise HTTPException(422, detail="earned_points exceeds max_points")
    exam.earned_points = payload.earned_points
    exam.confirmed_by_user = True
    db.commit()
    db.refresh(exam)
    return {
        "id": exam.id,
        "subject": exam.subject,
        "title": exam.title,
        "exam_date": str(exam.exam_date),
        "earned_points": exam.earned_points,
        "max_points": exam.max_points,
        "confirmed_by_user": exam.confirmed_by_user,
        "knowledge_evidence_created": False,
    }

CORE_SUBJECTS = ("math", "chinese", "english", "physics")


def _serialize_school_exam_item(
    i: m.SchoolExamItem,
    knowledge_name: str | None = None,
    *,
    coach_turn_count: int = 0,
) -> dict:
    """统一序列化校考逐题明细（含失分、结构化复盘状态与自动解析草稿元数据）。"""
    parsed_ref = paper_parser.parse_structured_reflection_note(
        i.error_note,
        i.error_category,
        is_lost=(i.earned_points < i.max_points),
    )
    out = {
        "id": i.id,
        "question_label": i.question_label,
        "knowledge_id": i.knowledge_id,
        "earned_points": i.earned_points,
        "max_points": i.max_points,
        "lost_points": round(max(0.0, i.max_points - i.earned_points), 2),
        "scoring_origin": i.scoring_origin,
        "confirmed_by_user": i.confirmed_by_user,
        "error_category": i.error_category,
        "error_note": i.error_note,
        "reflection_status": parsed_ref["reflection_status"],
        "stuck_point": parsed_ref["stuck_point"],
        "fix_strategy": parsed_ref["fix_strategy"],
        "return_reason": parsed_ref["return_reason"],
        "draft_source_attachment_id": i.draft_source_attachment_id,
        "draft_confidence": i.draft_confidence,
        "draft_reason": i.draft_reason,
        "draft_knowledge_candidates": i.draft_knowledge_candidates,
        "stem_text": i.stem_text,
        "student_answer_text": i.student_answer_text,
        "stem_state": i.stem_state,
        "stem_source": i.stem_source,
        "coach_turn_count": coach_turn_count,
    }
    if knowledge_name is not None:
        out["knowledge_name"] = knowledge_name
    return out


def _serialize_school_exam_items_with_names(
    db: Session, subject: str, items: list[m.SchoolExamItem]
) -> list[dict]:
    """批量附带课标知识点中文名称及书童对话轮次计数序列化校考逐题记录。"""
    if not items:
        return []
    _, _, name_map, _ = _resolve_school_knowledge_meta(db, subject, {it.knowledge_id for it in items})
    item_ids = [it.id for it in items]
    cnt_rows = db.execute(
        select(
            m.SchoolReflectionCoachSession.school_exam_item_id,
            func.count(m.SchoolReflectionCoachTurn.id),
        )
        .join(
            m.SchoolReflectionCoachTurn,
            m.SchoolReflectionCoachTurn.session_id == m.SchoolReflectionCoachSession.id,
        )
        .where(m.SchoolReflectionCoachSession.school_exam_item_id.in_(item_ids))
        .group_by(m.SchoolReflectionCoachSession.school_exam_item_id)
    ).all()
    turn_counts = {str(r[0]): int(r[1]) for r in cnt_rows}
    return [
        _serialize_school_exam_item(
            it,
            knowledge_name=name_map.get(it.knowledge_id, it.knowledge_id),
            coach_turn_count=turn_counts.get(it.id, 0),
        )
        for it in items
    ]


def _apply_school_item_confirmation(item: m.SchoolExamItem, payload: SchoolItemConfirmIn) -> None:
    """校验并执行单条校考草稿的人工核对确认（确认后分数与考点均锁定不可变）。"""
    if item.confirmed_by_user:
        if payload.earned_points == item.earned_points:
            raise HTTPException(409, detail="SCHOOL_ITEM_ALREADY_CONFIRMED")
        raise HTTPException(409, detail="SCHOOL_ITEM_IMMUTABLE")
    if item.scoring_origin != "ocr_draft":
        # 经 API 不可达（manual_entry 建即确认）：防御绕过应用层、直改库产生的越界行，使其仍需人工裁决。
        raise HTTPException(409, detail="SCHOOL_ITEM_ALREADY_CONFIRMED")
    effective_max = payload.max_points if payload.max_points is not None else item.max_points
    if payload.earned_points > effective_max:
        raise HTTPException(422, detail="earned_points exceeds max_points")
    if payload.max_points is not None:
        item.max_points = payload.max_points
    if payload.knowledge_id is not None:
        item.knowledge_id = payload.knowledge_id
    item.earned_points = payload.earned_points
    if "error_note" in payload.model_fields_set:
        item.error_note = payload.error_note
    if "error_category" in payload.model_fields_set:
        item.error_category = payload.error_category
    if item.earned_points >= item.max_points:
        item.error_category = None
    item.confirmed_by_user = True
    item.confirmed_at = m.now()


def _persist_draft_items(
    db: Session,
    exam: m.SchoolExam,
    draft_dicts: list[dict],
    *,
    replace_all_unconfirmed: bool = False,
    replace_matching_unconfirmed: bool = False,
) -> tuple[list[m.SchoolExamItem], list[str]]:
    """落库校考待核对草稿：强制保留 ocr_draft + confirmed_by_user=False，永不覆盖已确认记录。"""
    incoming_labels = {str(d["question_label"]) for d in draft_dicts if d.get("question_label")}
    if replace_all_unconfirmed:
        db.execute(
            delete(m.SchoolExamItem).where(
                m.SchoolExamItem.school_exam_id == exam.id,
                m.SchoolExamItem.confirmed_by_user.is_(False),
                m.SchoolExamItem.scoring_origin == "ocr_draft",
            )
        )
        db.flush()
    elif replace_matching_unconfirmed and incoming_labels:
        db.execute(
            delete(m.SchoolExamItem).where(
                m.SchoolExamItem.school_exam_id == exam.id,
                m.SchoolExamItem.confirmed_by_user.is_(False),
                m.SchoolExamItem.scoring_origin == "ocr_draft",
                m.SchoolExamItem.question_label.in_(incoming_labels),
            )
        )
        db.flush()

    occupied_labels = set(
        db.execute(
            select(m.SchoolExamItem.question_label).where(m.SchoolExamItem.school_exam_id == exam.id)
        ).scalars().all()
    )
    created: list[m.SchoolExamItem] = []
    skipped_labels: list[str] = []
    for entry in draft_dicts:
        label = str(entry.get("question_label") or "").strip()
        if not label:
            continue
        if label in occupied_labels:
            skipped_labels.append(label)
            continue
        occupied_labels.add(label)
        earned = float(entry.get("earned_points") or 0.0)
        max_pts = float(entry.get("max_points") or 2.0)
        err_cat = entry.get("error_category") if earned < max_pts else None
        record = m.SchoolExamItem(
            school_exam_id=exam.id,
            question_label=label,
            knowledge_id=str(entry.get("knowledge_id") or "unmapped"),
            earned_points=earned,
            max_points=max_pts,
            scoring_origin="ocr_draft",
            confirmed_by_user=False,
            confirmed_at=None,
            error_category=err_cat,
            error_note=entry.get("error_note"),
            draft_source_attachment_id=entry.get("draft_source_attachment_id"),
            draft_confidence=entry.get("draft_confidence"),
            draft_reason=entry.get("draft_reason"),
            draft_knowledge_candidates=entry.get("draft_knowledge_candidates"),
        )
        created.append(record)
        db.add(record)
    db.commit()
    for rec in created:
        db.refresh(rec)
    return created, skipped_labels


def _resolve_school_knowledge_meta(
    db: Session, subject: str, raw_kids: set[str]
) -> tuple[bool, list[dict], dict[str, str], dict[str, list[str]]]:
    """为管理端校考分析解析知识点中文名与旧新编码映射（道法保留自定义主题原名）。"""
    if subject == "all":
        merged_nodes: list[dict] = []
        node_names: dict[str, str] = {}
        alias_map: dict[str, list[str]] = {}
        for core_subj in CORE_SUBJECTS:
            sub_nodes, _ = _load_effective_knowledge_nodes(db, core_subj)
            merged_nodes.extend(sub_nodes)
            for n in sub_nodes:
                node_names[n["code"]] = n["name"]
        name_map: dict[str, str] = {}
        for kid in raw_kids:
            if kid == "ethics.general":
                name_map[kid] = "道法综合主题"
                continue
            mapped: list[str] = []
            for core_subj in CORE_SUBJECTS:
                if kid.startswith(core_subj):
                    mapped = resolve_question_to_candidate_codes(core_subj, [kid])
                    break
            if not mapped:
                for core_subj in CORE_SUBJECTS:
                    mapped = resolve_question_to_candidate_codes(core_subj, [kid])
                    if mapped:
                        break
            if mapped:
                alias_map[kid] = mapped
            resolved = node_names.get(kid) or TAXONOMY_MAP.get(kid) or SYNTHETIC_MAP.get(kid)
            if not resolved and mapped:
                resolved = node_names.get(mapped[0]) or TAXONOMY_MAP.get(mapped[0])
            name_map[kid] = resolved or kid
        return True, merged_nodes, name_map, alias_map

    if subject not in CORE_SUBJECTS:
        name_map = {
            kid: ("道法综合主题" if kid == "ethics.general" else (TAXONOMY_MAP.get(kid) or SYNTHETIC_MAP.get(kid) or kid))
            for kid in raw_kids
        }
        return False, [], name_map, {}

    nodes, _ = _load_effective_knowledge_nodes(db, subject)
    node_names = {n["code"]: n["name"] for n in nodes}
    alias_map: dict[str, list[str]] = {}
    name_map: dict[str, str] = {}
    for kid in raw_kids:
        mapped = resolve_question_to_candidate_codes(subject, [kid])
        if mapped:
            alias_map[kid] = mapped
        resolved = node_names.get(kid) or TAXONOMY_MAP.get(kid) or SYNTHETIC_MAP.get(kid)
        if not resolved and mapped:
            resolved = node_names.get(mapped[0]) or TAXONOMY_MAP.get(mapped[0])
        name_map[kid] = resolved or kid
    return True, nodes, name_map, alias_map


@app.post("/api/school-exams/{exam_id}/items", status_code=201)
def add_school_exam_items(exam_id: str, payload: SchoolExamItemsIn, owner: str = Depends(require_admin), db: Session = Depends(get_db)):
    """逐题得分录入：manual_entry 即人工确认；ocr_draft 须再走人工确认（AC-EVI-02）。"""
    exam = db.get(m.SchoolExam, exam_id)
    if exam is None or exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")
    labels = [item.question_label for item in payload.items]
    if len(set(labels)) != len(labels):
        raise HTTPException(409, detail="SCHOOL_ITEM_LABEL_CONFLICT")
    records = []
    for item in payload.items:
        confirmed = item.scoring_origin == "manual_entry"
        candidates = (
            [c.model_dump() for c in item.draft_knowledge_candidates]
            if item.draft_knowledge_candidates is not None
            else None
        )
        record = m.SchoolExamItem(
            school_exam_id=exam.id,
            question_label=item.question_label,
            knowledge_id=item.knowledge_id,
            earned_points=item.earned_points,
            max_points=item.max_points,
            scoring_origin=item.scoring_origin,
            confirmed_by_user=confirmed,
            confirmed_at=m.now() if confirmed else None,
            error_category=item.error_category,
            error_note=item.error_note,
            draft_source_attachment_id=item.draft_source_attachment_id,
            draft_confidence=item.draft_confidence,
            draft_reason=item.draft_reason,
            draft_knowledge_candidates=candidates,
        )
        records.append(record)
        db.add(record)
    try:
        db.commit()
    except IntegrityError:
        # 跨批同卷同题号被唯一约束拦截；回滚保证无部分写入。
        db.rollback()
        raise HTTPException(409, detail="SCHOOL_ITEM_LABEL_CONFLICT")
    for record in records:
        db.refresh(record)
    return {
        "items": _serialize_school_exam_items_with_names(db, exam.subject, records),
        "evidence_created": sum(1 for r in records if r.confirmed_by_user),
    }


@app.post("/api/school-exams/{exam_id}/items/{item_id}/confirm")
def confirm_school_exam_item(exam_id: str, item_id: str, payload: SchoolItemConfirmIn, owner: str = Depends(require_admin), db: Session = Depends(get_db)):
    """仅 ocr_draft 草稿可人工确认（可修正得分、满分、考点与错因）；确认后不可变（INV-04）。"""
    exam = db.get(m.SchoolExam, exam_id)
    if exam is None or exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")
    item = db.get(m.SchoolExamItem, item_id)
    if item is None or item.school_exam_id != exam_id:
        raise HTTPException(404, detail="item not found")
    _apply_school_item_confirmation(item, payload)
    db.commit()
    db.refresh(item)
    return _serialize_school_exam_items_with_names(db, exam.subject, [item])[0]


@app.post("/api/school-exams/{exam_id}/items/confirm-batch")
def confirm_school_exam_items_batch(
    exam_id: str,
    payload: SchoolItemConfirmBatchIn,
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """批量人工确认本场校考草稿：任一条校验失败则整批回滚，绝不部分提交。"""
    exam = db.get(m.SchoolExam, exam_id)
    if exam is None or exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")
    item_ids = [entry.item_id for entry in payload.items]
    if len(set(item_ids)) != len(item_ids):
        raise HTTPException(409, detail="SCHOOL_ITEM_DUPLICATE_CONFIRM")
    rows = db.execute(
        select(m.SchoolExamItem).where(
            m.SchoolExamItem.school_exam_id == exam.id,
            m.SchoolExamItem.id.in_(item_ids),
        )
    ).scalars().all()
    by_id = {row.id: row for row in rows}
    updated: list[m.SchoolExamItem] = []
    for entry in payload.items:
        item = by_id.get(entry.item_id)
        if item is None:
            db.rollback()
            raise HTTPException(404, detail="item not found")
        _apply_school_item_confirmation(item, entry)
        updated.append(item)
    db.commit()
    for row in updated:
        db.refresh(row)
    return {
        "items": _serialize_school_exam_items_with_names(db, exam.subject, updated),
        "evidence_created": len(updated),
    }


@app.post("/api/school-exams/{exam_id}/items/{item_id}/discard")
def discard_school_exam_item(
    exam_id: str,
    item_id: str,
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """丢弃未人工确认的 ocr_draft 识别草稿；已确认题目不可撤销或删除（INV-04）。"""
    exam = db.get(m.SchoolExam, exam_id)
    if exam is None or exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")
    item = db.get(m.SchoolExamItem, item_id)
    if item is None or item.school_exam_id != exam_id:
        raise HTTPException(404, detail="item not found")
    if item.confirmed_by_user or item.scoring_origin != "ocr_draft":
        raise HTTPException(409, detail="SCHOOL_ITEM_IMMUTABLE")
    label = item.question_label
    db.delete(item)
    db.commit()
    return {"status": "discarded", "id": item_id, "question_label": label}


def _infer_attachment_subject(filename: str, fallback: str = "math") -> str:
    return exam_pipeline.infer_attachment_subject(filename, fallback=fallback)


_SUBJECT_CN_PREFIX: dict[str, str] = {
    "chinese": "语文",
    "math": "数学",
    "english": "英语",
    "physics": "物理",
    "ethics": "道德与法治",
}


@app.post("/api/school-exams/{exam_id}/parse-drafts")
def parse_school_exam_drafts(
    exam_id: str,
    payload: SchoolExamParseDraftsIn,
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """从校考已上传附件自动抽取 M2 逐题草稿（永不直接确认入画像）。"""
    exam = db.get(m.SchoolExam, exam_id)
    if exam is None or exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")
    unique_ids = list(dict.fromkeys(payload.attachment_ids))
    rows = db.execute(
        select(m.SchoolPaperAttachment).where(
            m.SchoolPaperAttachment.school_exam_id == exam.id,
            m.SchoolPaperAttachment.owner_id == owner,
            m.SchoolPaperAttachment.id.in_(unique_ids),
        )
    ).scalars().all()
    att_map = {att.id: att for att in rows}
    if len(att_map) != len(unique_ids):
        raise HTTPException(404, detail="ATTACHMENT_NOT_FOUND")
    attachments = [att_map[aid] for aid in unique_ids]
    supported = {"application/pdf", "image/png", "image/jpeg", files.DOCX_MEDIA_TYPE}
    if any(att.media_type not in supported for att in attachments):
        raise HTTPException(422, detail="UNSUPPORTED_ATTACHMENT_FOR_PARSING")

    loaded = [
        {
            "id": att.id,
            "filename": att.filename,
            "media_type": att.media_type,
            "data": files.load_blob(att),
            "subject": exam.subject if exam.subject != "all" else _infer_attachment_subject(att.filename),
        }
        for att in attachments
    ]

    catalog_by_subj: dict[str, list[dict]] = {}

    def _catalog_for(subj: str) -> list[dict]:
        if subj not in catalog_by_subj:
            _, cat, _, _ = _resolve_school_knowledge_meta(db, subj, set())
            catalog_by_subj[subj] = cat
        return catalog_by_subj[subj]

    def _prefix_if_all(subj: str, row: dict) -> dict:
        if exam.subject == "all":
            cn = _SUBJECT_CN_PREFIX.get(subj)
            lbl = str(row.get("question_label") or "").strip()
            if cn and lbl and not any(lbl.startswith(f"{p}·") for p in _SUBJECT_CN_PREFIX.values()):
                row = {**row, "question_label": f"{cn}·{lbl}"[:160]}
        return row

    def _collect_skeleton() -> list[dict]:
        combined: list[dict] = []
        seen_lbls: set[str] = set()
        for item in loaded:
            text = paper_parser.extract_embedded_text(item["data"], item["media_type"])
            if not text:
                continue
            item_subj = item["subject"]
            for raw_row in paper_parser.parse_paper_skeleton_from_text(
                text, item_subj, _catalog_for(item_subj), attachment_id=item["id"]
            ):
                row = _prefix_if_all(item_subj, raw_row)
                if row["question_label"] not in seen_lbls:
                    seen_lbls.add(row["question_label"])
                    combined.append(row)
        return combined

    meta: dict = {"pages_sent": 0, "masked_pages": 0}
    if payload.mode == "skeleton_only":
        draft_items = _collect_skeleton()
        if not draft_items:
            raise HTTPException(422, detail="NO_EMBEDDED_TEXT_FOR_SKELETON")
        parser_mode_used = "local_text_skeleton"
    else:
        cfg = paper_parser.load_vision_config(require_key=False)
        visual_attachments = [it for it in loaded if it["media_type"] != files.DOCX_MEDIA_TYPE]
        if cfg is not None and visual_attachments:
            draft_items = []
            seen_v_lbls: set[str] = set()
            by_subj_vis: dict[str, list[dict]] = {}
            for it in visual_attachments:
                by_subj_vis.setdefault(it["subject"], []).append(it)
            try:
                for vis_subj, vis_list in by_subj_vis.items():
                    sub_items, sub_meta = paper_parser.parse_items_with_deepseek_vision(
                        subject=vis_subj,
                        knowledge_catalog=_catalog_for(vis_subj),
                        attachments=vis_list,
                        mask_student_header=payload.mask_student_header,
                        cfg=cfg,
                    )
                    meta["pages_sent"] = int(meta.get("pages_sent") or 0) + int(sub_meta.get("pages_sent") or 0)
                    meta["masked_pages"] = int(meta.get("masked_pages") or 0) + int(sub_meta.get("masked_pages") or 0)
                    meta["model"] = sub_meta.get("model")
                    for raw_row in sub_items:
                        row = _prefix_if_all(vis_subj, raw_row)
                        if row["question_label"] not in seen_v_lbls:
                            seen_v_lbls.add(row["question_label"])
                            draft_items.append(row)
            except paper_parser.VisionParserConfigError as exc:
                raise HTTPException(503, detail=str(exc)) from exc
            except paper_parser.VisionParserUnavailableError as exc:
                raise HTTPException(503, detail=str(exc)) from exc
            parser_mode_used = f"deepseek_vision:{cfg.vision_model}"
        else:
            # 密钥未配置或全为纯文字卷时：仅当选中附件全部可本地抽骨架且非扫描图片时，优雅回退本地规则。
            has_unparsed_visual = any(
                it["media_type"] in ("image/png", "image/jpeg")
                or not paper_parser.extract_embedded_text(it["data"], it["media_type"])
                for it in loaded
            )
            if has_unparsed_visual:
                raise HTTPException(503, detail="VISION_PARSER_NOT_CONFIGURED")
            draft_items = _collect_skeleton()
            if not draft_items:
                raise HTTPException(422, detail="NO_EMBEDDED_TEXT_FOR_SKELETON")
            parser_mode_used = "local_text_skeleton_fallback"

    created, skipped_labels = _persist_draft_items(
        db,
        exam,
        draft_items,
        replace_all_unconfirmed=payload.replace_unconfirmed_drafts,
    )
    return {
        "parser_mode_used": parser_mode_used,
        "meta": meta,
        "created_items": _serialize_school_exam_items_with_names(db, exam.subject, created),
        "skipped_labels": skipped_labels,
        "evidence_created": 0,
    }


@app.post("/api/school-exams/{exam_id}/sync-drafts")
def sync_school_exam_drafts(
    exam_id: str,
    payload: SchoolExamSyncDraftsIn,
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """接收外部校考平台（如 k12100.com）安全抓取的逐题得分并生成待人工确认草稿。"""
    exam = db.get(m.SchoolExam, exam_id)
    if exam is None or exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")
    _, knowledge_catalog, _, _ = _resolve_school_knowledge_meta(db, exam.subject, set())
    enriched_items, enrich_mode = paper_parser.enrich_external_items_with_deepseek(
        subject=exam.subject,
        knowledge_catalog=knowledge_catalog,
        external_items=[it.model_dump() for it in payload.items],
        use_ai=payload.use_ai,
    )
    created, skipped_labels = _persist_draft_items(
        db,
        exam,
        enriched_items,
        replace_matching_unconfirmed=payload.replace_unconfirmed_drafts,
    )
    return {
        "source_name": payload.source_name,
        "parser_mode_used": enrich_mode,
        "created_items": _serialize_school_exam_items_with_names(db, exam.subject, created),
        "skipped_labels": skipped_labels,
        "evidence_created": 0,
    }


@app.get("/api/school-exams/k12100-sync/status")
def get_k12100_sync_status(owner: str = Depends(require_admin)):
    """查询当前运行环境的 k12100 直连采集能力、脱敏凭据状态与最近任务快照。"""
    _ = owner
    return k12100_backfill.get_k12100_runtime_status()


@app.post("/api/school-exams/k12100-sync/jobs", status_code=202)
def start_k12100_sync_job_endpoint(
    payload: K12100SyncJobStartIn,
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """手动触发宿主机持久化浏览器单次采集与全科补全任务（容器隔离或并发时返回 409）。"""
    return k12100_backfill.start_k12100_sync_job(
        db,
        owner=owner,
        resolve_knowledge_fn=_resolve_school_knowledge_meta,
        persist_drafts_fn=_persist_draft_items,
        save_paper_fn=save_school_paper,
        exam_keyword=payload.exam_keyword,
        target_exam_date=payload.target_exam_date,
        series_title_prefix=payload.series_title_prefix,
        max_exams=payload.max_exams,
        confirm_total_scores=payload.confirm_total_scores,
        extract_existing_pdfs=payload.extract_existing_pdfs,
        upload_missing_cards=payload.upload_missing_cards,
        replace_unconfirmed_drafts=payload.replace_unconfirmed_drafts,
        use_ai=payload.use_ai,
        headless=payload.headless,
        archive_exam_id=payload.archive_exam_id,
    )


@app.post("/api/school-exams/k12100-sync/report-jobs", status_code=202)
def start_k12100_report_sync_job_endpoint(
    payload: K12100ReportJobStartIn | None = None,
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """从 k12100 首页读取场次日期并下载未同步场次的「总分」分析报告，新建/更新/补全考试档案与草稿。"""
    opts = payload or K12100ReportJobStartIn()
    return k12100_report_sync.start_k12100_report_job(
        db,
        owner=owner,
        auto_map_fn=_auto_map_report_items,
        max_exams=opts.max_exams,
        headless=opts.headless,
        archive_exam_id=opts.archive_exam_id,
    )


@app.post("/api/school-exams/k12100-sync/hydrate-local")
def hydrate_k12100_local_reports_endpoint(
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """不联网 k12100：无损合并历史重复报告并从本地已存 PDF 补全排名、班级/年级最高分及缺失答题卡。"""
    summary = report_pipeline.hydrate_incomplete_local_reports(
        db,
        owner=owner,
        auto_map_fn=_auto_map_report_items,
    )
    center = exam_pipeline.get_sync_center(db, owner=owner)
    return {**summary, "synced_reports": center["synced_reports"], "sync_readiness": center["sync_readiness"]}


@app.get("/api/school-exams/k12100-sync/jobs/{job_id}")
def get_k12100_sync_job_endpoint(job_id: str, owner: str = Depends(require_admin)):
    """轮询单个手动同步任务的进度与逐科结果摘要。"""
    _ = owner
    job = k12100_backfill.get_k12100_sync_job(job_id)
    if job is None:
        raise HTTPException(404, detail="K12100_SYNC_JOB_NOT_FOUND")
    return job


def _get_owned_paper(db: Session, paper_id: str, owner: str) -> m.SchoolExamPaper:
    paper = db.get(m.SchoolExamPaper, paper_id)
    if paper is None or paper.learner_id != owner:
        raise HTTPException(404, detail="SCHOOL_EXAM_PAPER_NOT_FOUND")
    return paper


def _raise_pipeline_error(exc: exam_pipeline.PaperPipelineError):
    status_code = 409 if exc.code in {
        exam_pipeline.SOURCE_NOT_CONFIGURED,
        "INBOX_PERMISSIONS_TOO_WIDE",
        "SOURCE_SYMLINK_REJECTED",
        "INBOX_SYMLINK_REJECTED",
    } else 422
    raise HTTPException(status_code=status_code, detail=exc.code)


@app.get("/api/school-exams/sync-center")
def get_school_exam_sync_center(
    exam_id: str | None = Query(default=None, max_length=64),
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """返回四步同步中心的真实后端状态：卷源、扫描、试卷与严格匹配候选。"""
    try:
        return exam_pipeline.get_sync_center(db, owner=owner, exam_id=exam_id)
    except exam_pipeline.PaperPipelineError as exc:
        _raise_pipeline_error(exc)
    except HomeIdentityError as exc:
        raise HTTPException(409, detail="ENVIRONMENT_IDENTITY_INVALID") from exc


@app.post("/api/school-exams/reports/scan")
def scan_school_exam_reports(
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """扫描当前环境 inbox 中的分析报告册；报告不会当作单科试卷导入。"""
    return report_pipeline.scan_reports(db, owner=owner)


@app.post("/api/school-exams/reports/{report_id}/match")
def match_school_exam_report(report_id: str, owner: str = Depends(require_admin), db: Session = Depends(get_db)):
    report = db.get(m.SchoolExamReport, report_id)
    if report is None or report.learner_id != owner:
        raise HTTPException(404, detail="report not found")
    result = report_pipeline.match_report(db, report=report)
    db.commit()
    db.refresh(report)
    return {"report": report_pipeline.serialize_report(report), "match": result}


@app.get("/api/school-exams/reports")
def list_school_exam_reports(owner: str = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.execute(
        select(m.SchoolExamReport).where(m.SchoolExamReport.learner_id == owner).order_by(m.SchoolExamReport.created_at.desc())
    ).scalars().all()
    return [report_pipeline.serialize_report(item) for item in exam_pipeline.select_canonical_reports(rows)]


def _auto_associate_exam_items(
    db: Session,
    exam: m.SchoolExam,
    *,
    use_ai: bool = True,
    overwrite_existing: bool = False,
) -> dict[str, int]:
    """为校考未确认明细补全所属知识点与 Top-3 候选考点（绝不改写已确认小题）。"""
    rows = sorted(
        db.execute(select(m.SchoolExamItem).where(m.SchoolExamItem.school_exam_id == exam.id)).scalars().all(),
        key=lambda it: question_label_sort_key(it.question_label),
    )
    if not rows:
        return {"updated": 0, "tier1_matched": 0, "tier2_ai": 0, "tier3_inferred": 0, "skipped_confirmed": 0}

    _has_taxonomy, nodes, _names, _aliases = _resolve_school_knowledge_meta(db, exam.subject, set())
    attachments = db.execute(
        select(m.SchoolPaperAttachment).where(
            m.SchoolPaperAttachment.school_exam_id == exam.id,
            m.SchoolPaperAttachment.owner_id == exam.learner_id,
        )
    ).scalars().all()
    by_number: dict[str, str] = {}
    ordered_attachments = sorted(attachments, key=lambda a: (1 if "答题卡" in a.filename else 0, a.created_at, a.id))
    for att in ordered_attachments:
        if by_number:
            break
        try:
            data = files.attachment_file_path(att).read_bytes()
            text = paper_parser.extract_embedded_text(data, att.media_type)
        except Exception:
            text = ""
        if not text:
            continue
        for parsed in paper_parser.parse_paper_skeleton_from_text(text, exam.subject, nodes, attachment_id=att.id):
            m_num = re.search(r"(\d+)", str(parsed.get("question_label") or ""))
            stem = str(parsed.get("stem") or "").strip()
            if m_num and stem and m_num.group(1) not in by_number:
                by_number[m_num.group(1)] = stem

    skipped_confirmed = 0
    targets: list[m.SchoolExamItem] = []
    payload_rows: list[dict] = []
    for row in rows:
        if row.confirmed_by_user:
            skipped_confirmed += 1
            continue
        m_num = re.search(r"(\d+)", str(row.question_label or ""))
        stem = by_number.get(m_num.group(1), "") if m_num else ""
        has_kid = bool(row.knowledge_id and row.knowledge_id != "unmapped")
        has_three_cands = isinstance(row.draft_knowledge_candidates, list) and len(row.draft_knowledge_candidates) >= 3
        can_upgrade_inferred = row.draft_confidence == "type_inferred" and bool(stem)
        if not overwrite_existing and has_kid and has_three_cands and not can_upgrade_inferred:
            continue
        targets.append(row)
        payload_rows.append(
            {
                "question_label": row.question_label,
                "max_points": row.max_points,
                "stem_text": stem,
                "draft_reason": row.draft_reason,
                "knowledge_id": row.knowledge_id,
            }
        )

    if not targets:
        return {"updated": 0, "tier1_matched": 0, "tier2_ai": 0, "tier3_inferred": 0, "skipped_confirmed": skipped_confirmed}

    if exam.subject == "all":
        att_subj_by_id = {
            att.id: _infer_attachment_subject(att.filename)
            for att in attachments
        }
        targets_by_subj: dict[str, list[tuple[m.SchoolExamItem, dict]]] = {}
        for row, p_row in zip(targets, payload_rows):
            inferred = _infer_school_item_subject(row.question_label, None)
            if not inferred and row.draft_source_attachment_id:
                inferred = att_subj_by_id.get(row.draft_source_attachment_id)
            if not inferred:
                inferred = _infer_school_item_subject(row.question_label, row.knowledge_id) or "math"
            targets_by_subj.setdefault(inferred, []).append((row, p_row))
    else:
        targets_by_subj = {exam.subject: list(zip(targets, payload_rows))}

    updated = 0
    tier1 = 0
    tier2 = 0
    tier3 = 0

    for item_subj, pair_list in targets_by_subj.items():
        _, subj_nodes, _, _ = _resolve_school_knowledge_meta(db, item_subj, set())
        subj_targets = [pair[0] for pair in pair_list]
        subj_payloads = [pair[1] for pair in pair_list]
        assocs = paper_parser.auto_associate_school_items(
            subject=item_subj,
            knowledge_catalog=subj_nodes,
            items=subj_payloads,
            use_ai=use_ai,
        )
        valid_names = {str(n["code"]): str(n.get("name") or n["code"]) for n in subj_nodes if n.get("code")}

        for row, assoc in zip(subj_targets, assocs):
            has_kid = bool(row.knowledge_id and row.knowledge_id != "unmapped")
            cands = assoc["draft_knowledge_candidates"]
            if not overwrite_existing and has_kid and row.draft_confidence != "type_inferred":
                existing_first = [
                    {
                        "knowledge_id": row.knowledge_id,
                        "title": valid_names.get(row.knowledge_id, row.knowledge_id),
                        "reason": "保留既有已选考点",
                    }
                ]
                row.draft_knowledge_candidates = paper_parser.ensure_three_candidates(
                    existing_first,
                    subject=item_subj,
                    knowledge_catalog=subj_nodes,
                    question_label=row.question_label,
                    max_points=row.max_points,
                    fallback_candidates=cands,
                )
                updated += 1
                continue

            row.knowledge_id = assoc["knowledge_id"]
            row.draft_knowledge_candidates = cands
            row.draft_confidence = assoc["draft_confidence"]
            basis = str(assoc.get("basis_note") or "").strip()
            if basis:
                base_reason = re.sub(r"；(?:[^；]*先验|[^；]*命中[^；]*|AI语义:[^；]*)$", "", str(row.draft_reason or "").strip())
                row.draft_reason = f"{base_reason}；{basis}"[:500] if base_reason else basis[:500]
            method = assoc.get("method")
            if method == "auto_matched":
                tier1 += 1
            elif method == "ai_matched":
                tier2 += 1
            else:
                tier3 += 1
            updated += 1

    return {
        "updated": updated,
        "tier1_matched": tier1,
        "tier2_ai": tier2,
        "tier3_inferred": tier3,
        "skipped_confirmed": skipped_confirmed,
    }


def _auto_map_report_items(db: Session, report: m.SchoolExamReport) -> int:
    """用已归档原卷文字层及考纲先验自动关联报告草稿知识点与 Top-3 候选，只填候选，不确认。"""
    links = {str(link.get("subject")): str(link.get("exam_id")) for link in (report.linked_exam_ids or [])}
    applied = 0
    for exam_id in links.values():
        exam = db.get(m.SchoolExam, exam_id)
        if exam is None or exam.learner_id != report.learner_id:
            continue
        summary = _auto_associate_exam_items(db, exam, use_ai=False, overwrite_existing=False)
        applied += summary["updated"]
    return applied


@app.post("/api/school-exams/reports/{report_id}/items/drafts")
def generate_school_exam_report_item_drafts(
    report_id: str,
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """把报告逐题表生成为台账 ocr_draft；知识点待人工映射，不自动确认。"""
    report = db.get(m.SchoolExamReport, report_id)
    if report is None or report.learner_id != owner:
        raise HTTPException(404, detail="report not found")
    result = report_pipeline.generate_item_drafts(db, report=report)
    result["auto_mapped"] = _auto_map_report_items(db, report)
    db.commit()
    return result


@app.post("/api/school-exams/reports/{report_id}/items/ai-map")
def ai_map_school_exam_report_items(
    report_id: str,
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """DeepSeek 文本知识点匹配；只传题干和编码清单，只写未确认候选。"""
    report = db.get(m.SchoolExamReport, report_id)
    if report is None or report.learner_id != owner:
        raise HTTPException(404, detail="report not found")
    return report_pipeline.ai_map_report_items(db, report=report)


@app.post("/api/school-exams/reports/{report_id}/subjects")
def supplement_school_exam_report_subject(
    report_id: str,
    payload: SchoolExamReportSubjectIn,
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """为报告补录缺失学科统计；只改报告草稿，不创建原卷/不写能力画像。"""
    report = db.get(m.SchoolExamReport, report_id)
    if report is None or report.learner_id != owner:
        raise HTTPException(404, detail="report not found")
    subjects = [dict(item) for item in (report.subjects or [])]
    if any(str(item.get("subject")) == payload.subject for item in subjects):
        raise HTTPException(409, detail="REPORT_SUBJECT_ALREADY_PRESENT")
    subjects.append(
        {
            "subject": payload.subject,
            "name": {"chinese": "语文", "math": "数学", "english": "英语", "physics": "物理", "ethics": "道德与法治"}.get(payload.subject, payload.subject),
            "score": payload.score,
            "max_score": payload.max_score,
            "class_rank": payload.class_rank,
            "grade_rank": payload.grade_rank,
            "participants": payload.participants,
            "class_highest": payload.class_highest,
            "grade_highest": payload.grade_highest,
            "page": None,
            "source": "manual_supplement",
        }
    )
    report.subjects = subjects
    report.listed_subject_score = round(sum(float(item.get("score") or 0) for item in subjects), 2)
    report.listed_subject_max = round(sum(float(item.get("max_score") or 0) for item in subjects), 2)
    if report.report_total_score is None or report.report_total_max is None:
        report.scope_status = "NEEDS_REVIEW"
    elif abs(report.report_total_score - report.listed_subject_score) < 0.01 and abs(report.report_total_max - report.listed_subject_max) < 0.01:
        report.scope_status = "CONSISTENT"
    elif abs(report.report_total_score - report.listed_subject_score) < 0.01:
        report.scope_status = "DIFFERENT_SCOPE_POSSIBLE"
    else:
        report.scope_status = "UNEXPLAINED"
    report.status = "needs_review"
    report.match_state = "NEEDS_REVIEW"
    report.updated_at = m.now()
    db.commit()
    db.refresh(report)
    return report_pipeline.serialize_report(report)


@app.post("/api/school-exams/reports/{report_id}/confirm")
def confirm_school_exam_report(
    report_id: str,
    payload: SchoolExamReportConfirmIn,
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """人工确认报告；必须先完成唯一关联，只改变报告状态，不改写成绩或画像。"""
    report = db.get(m.SchoolExamReport, report_id)
    if report is None or report.learner_id != owner:
        raise HTTPException(404, detail="report not found")
    if not payload.confirmed:
        raise HTTPException(422, detail="REPORT_CONFIRMATION_REQUIRED")
    if report.match_state not in {"EXACT_MATCH", "PARTIAL_MATCH"}:
        raise HTTPException(409, detail="REPORT_MATCH_REQUIRED")
    ledger = report_pipeline.apply_report_to_ledger(db, report=report)
    ledger["answer_cards_synced"] = report_pipeline.sync_answer_cards_to_ledger(db, report=report)
    report.status = "confirmed"
    report.updated_at = m.now()
    db.commit()
    db.refresh(report)
    return {**report_pipeline.serialize_report(report), "ledger": ledger}


@app.patch("/api/school-exams/reports/{report_id}")
def patch_school_exam_report(
    report_id: str,
    payload: SchoolExamReportPatchIn,
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """人工补录报告身份字段（如 OCR 缺失的年级）；不写关联考试、成绩或画像。"""
    report = db.get(m.SchoolExamReport, report_id)
    if report is None or report.learner_id != owner:
        raise HTTPException(404, detail="report not found")
    updates = payload.model_dump(exclude_unset=True)
    for name, value in updates.items():
        setattr(report, name, value)
    report.status = "needs_review" if report.status == "confirmed" else report.status
    report.updated_at = m.now()
    db.commit()
    db.refresh(report)
    return report_pipeline.serialize_report(report)


@app.post("/api/school-exams/reports/{report_id}/answer-cards")
def build_report_answer_cards(
    report_id: str,
    rotation: int = Query(0),
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    report = db.get(m.SchoolExamReport, report_id)
    if report is None or report.learner_id != owner:
        raise HTTPException(404, detail="report not found")
    return report_pipeline.build_answer_card_attachments(db, report=report, rotation=rotation)


@app.get("/api/school-exams/reports/{report_id}/answer-cards")
def list_report_answer_cards(report_id: str, owner: str = Depends(require_admin), db: Session = Depends(get_db)):
    report = db.get(m.SchoolExamReport, report_id)
    if report is None or report.learner_id != owner:
        raise HTTPException(404, detail="report not found")
    return report_pipeline.list_answer_card_attachments(db, report=report)


@app.get("/api/school-exams/reports/{report_id}/answer-cards/{attachment_id}/image")
def get_report_answer_card_image(
    report_id: str,
    attachment_id: str,
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    report = db.get(m.SchoolExamReport, report_id)
    if report is None or report.learner_id != owner:
        raise HTTPException(404, detail="report not found")
    attachment = db.get(m.SchoolExamReportAttachment, attachment_id)
    if attachment is None or attachment.report_id != report_id or attachment.learner_id != owner:
        raise HTTPException(404, detail="attachment not found")
    try:
        data = files.attachment_file_path(attachment).read_bytes()
    except FileNotFoundError as exc:
        raise HTTPException(409, detail="ATTACHMENT_FILE_MISSING") from exc
    if attachment.rotation:
        from io import BytesIO
        from PIL import Image

        try:
            with Image.open(BytesIO(data)) as image:
                rotated = image.convert("RGB").rotate(-int(attachment.rotation), expand=True)
                output = BytesIO()
                rotated.save(output, format="PNG")
                data = output.getvalue()
        except Exception as exc:
            raise HTTPException(409, detail="ANSWER_CARD_ROTATION_FAILED") from exc
    return Response(content=data, media_type=attachment.media_type)


@app.get("/api/school-exams/reports/{report_id}")
def get_school_exam_report(report_id: str, owner: str = Depends(require_admin), db: Session = Depends(get_db)):
    report = db.get(m.SchoolExamReport, report_id)
    if report is None or report.learner_id != owner:
        raise HTTPException(404, detail="report not found")
    return report_pipeline.serialize_report(report)


@app.post("/api/school-exams/pipeline/scan")
def scan_school_exam_papers(
    payload: SchoolPaperScanIn | None = None,
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """扫描当前环境 0700 校考目录（优先选中档案 exam-paper/，否则 inbox/）；所有原卷先待核对，逐题仍走既有 ocr_draft 门禁。"""
    try:
        return exam_pipeline.scan_local_papers(
            db,
            owner=owner,
            apply_imports=bool(payload and payload.apply_imports),
            exam_id=payload.exam_id if payload else None,
        )
    except exam_pipeline.PaperPipelineError as exc:
        _raise_pipeline_error(exc)
    except HomeIdentityError as exc:
        raise HTTPException(409, detail="ENVIRONMENT_IDENTITY_INVALID") from exc


@app.post("/api/school-exams/pipeline/acquire")
def acquire_school_exam_papers(owner: str = Depends(require_admin), db: Session = Depends(get_db)):
    """通过已登记授权适配器获取并扫描试卷；未配置真实来源时明确返回 SOURCE_NOT_CONFIGURED。"""
    try:
        acquired = exam_pipeline.acquire_from_configured_source()
        scanned = exam_pipeline.scan_local_papers(db, owner=owner, apply_imports=False, source_kind="acquired")
        return {**acquired, "scan": scanned["run"], "papers": scanned["papers"]}
    except exam_pipeline.PaperPipelineError as exc:
        _raise_pipeline_error(exc)


@app.post("/api/school-exams/pipeline/papers/{paper_id}/match")
def match_school_exam_paper(
    paper_id: str,
    payload: SchoolPaperMatchIn,
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """重跑严格匹配，或由管理员显式选择候选考试并确认。"""
    paper = _get_owned_paper(db, paper_id, owner)
    try:
        if payload.exam_id:
            return exam_pipeline.manual_match_paper(
                db,
                paper=paper,
                owner=owner,
                exam_id=payload.exam_id,
                confirmed_by_human=payload.confirmed_by_human,
            )
        return exam_pipeline.rematch_paper(db, paper=paper)
    except exam_pipeline.PaperPipelineError as exc:
        _raise_pipeline_error(exc)


@app.post("/api/school-exams/pipeline/papers/{paper_id}/import")
def import_school_exam_paper(
    paper_id: str,
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """把唯一精确匹配/人工确认的试卷复制为私有校卷附件；不修改总分或已确认历史。"""
    paper = _get_owned_paper(db, paper_id, owner)
    try:
        return exam_pipeline.import_matched_paper(db, paper=paper, owner=owner)
    except exam_pipeline.PaperPipelineError as exc:
        _raise_pipeline_error(exc)


@app.post("/api/school-exams/pipeline/papers/{paper_id}/collect", status_code=202)
def collect_school_exam_paper(
    paper_id: str,
    payload: SchoolPaperCollectIn | None = None,
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """从唯一匹配/人工确认的试卷启动单场 k12100 采集，闭合本地匹配到待核对入库的流程。"""
    paper = _get_owned_paper(db, paper_id, owner)
    if paper.status not in {"matched", "imported"} or not paper.school_exam_id:
        raise HTTPException(409, detail="SCHOOL_EXAM_MATCH_REQUIRED")
    exam = db.get(m.SchoolExam, paper.school_exam_id)
    if exam is None or exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")
    # 本地档案标题不是平台可信关键词；不要用它筛空真实场次。
    # 采集最近单场后由五字段严格匹配决定是否入账，匹配不到即阻断。
    options = payload or SchoolPaperCollectIn()
    return k12100_backfill.start_k12100_sync_job(
        db,
        owner=owner,
        resolve_knowledge_fn=_resolve_school_knowledge_meta,
        persist_drafts_fn=_persist_draft_items,
        save_paper_fn=save_school_paper,
        exam_keyword=None,
        target_exam_date=None,
        series_title_prefix=None,
        max_exams=1,
        confirm_total_scores=False,
        extract_existing_pdfs=options.extract_existing_pdfs,
        upload_missing_cards=options.upload_missing_cards,
        replace_unconfirmed_drafts=options.replace_unconfirmed_drafts,
        use_ai=options.use_ai,
        headless=options.headless,
    )


@app.post("/api/school-exams/pipeline/papers/{paper_id}/reject")
def reject_school_exam_paper(
    paper_id: str,
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """人工忽略无法确认身份的试卷；只改本索引状态，绝不删除原始文件。"""
    paper = _get_owned_paper(db, paper_id, owner)
    if paper.status == "imported":
        raise HTTPException(409, detail="PAPER_ALREADY_IMPORTED")
    paper.status = "rejected"
    paper.match_state = "REJECTED"
    paper.updated_at = m.now()
    db.commit()
    db.refresh(paper)
    return {"paper": exam_pipeline.serialize_paper(paper)}


@app.get("/api/school-exams/{exam_id}/ranks")
def get_school_exam_ranks(exam_id: str, owner: str = Depends(require_admin), db: Session = Depends(get_db)):
    """本人排名独立查询（仅管理端）；不进入学生端响应或能力画像。"""
    exam = db.get(m.SchoolExam, exam_id)
    if exam is None or exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")
    return exam_pipeline.rank_payload(db, exam=exam, owner=owner)


@app.post("/api/school-exams/{exam_id}/ranks/{rank_id}/confirm")
def confirm_school_exam_rank(
    exam_id: str,
    rank_id: str,
    payload: SchoolExamRankConfirmIn,
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """人工确认平台本人排名事实；只更新核对状态，不修改排名值或能力证据。"""
    _ = payload
    return exam_pipeline.confirm_rank(db, rank_id=rank_id, owner=owner, exam_id=exam_id)


@app.post(
    "/api/school-exams/k12100-sync/import-bundle",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": K12100ImportBundleIn.model_json_schema(),
                }
            },
        }
    },
)
async def import_k12100_bundle_endpoint(
    request: Request,
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """导入宿主机导出的脱敏 k12100 采集包（≤ 15 MiB），跨环境统一执行全科建档/提干与草稿入库。"""
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > k12100_backfill.MAX_BUNDLE_BODY_BYTES:
            raise HTTPException(413, detail="K12100_BUNDLE_TOO_LARGE")
        raw.extend(chunk)
    try:
        payload = K12100ImportBundleIn.model_validate_json(bytes(raw))
    except Exception as exc:
        raise HTTPException(422, detail="K12100_INVALID_BUNDLE") from exc

    return await run_in_threadpool(
        k12100_backfill.apply_k12100_bundle,
        db,
        owner=owner,
        raw_bundle=payload.bundle,
        resolve_knowledge_fn=_resolve_school_knowledge_meta,
        persist_drafts_fn=_persist_draft_items,
        save_paper_fn=save_school_paper,
        exam_keyword=payload.exam_keyword,
        target_exam_date=payload.target_exam_date,
        series_title_prefix=payload.series_title_prefix,
        max_exams=payload.max_exams,
        confirm_total_scores=payload.confirm_total_scores,
        extract_existing_pdfs=payload.extract_existing_pdfs,
        upload_missing_cards=payload.upload_missing_cards,
        replace_unconfirmed_drafts=payload.replace_unconfirmed_drafts,
        use_ai=payload.use_ai,
        archive_exam_id=payload.archive_exam_id,
    )

@app.post("/api/school-exams/{exam_id}/items/auto-associate", response_model=SchoolExamAutoAssociateOut)
def auto_associate_school_exam_items(
    exam_id: str,
    payload: SchoolExamAutoAssociateIn | None = None,
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """按三层混合管线为校考待核对明细补全所属知识点与 Top-3 候选考点；只写草稿，绝不自动确认。"""
    exam = db.get(m.SchoolExam, exam_id)
    if exam is None or exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")
    opts = payload or SchoolExamAutoAssociateIn()
    summary = _auto_associate_exam_items(
        db,
        exam,
        use_ai=opts.use_ai,
        overwrite_existing=opts.overwrite_existing,
    )
    db.commit()
    return SchoolExamAutoAssociateOut(**summary)


@app.post("/api/school-exams/{exam_id}/items/{item_id}/analysis")
def update_school_exam_item_analysis(
    exam_id: str,
    item_id: str,
    payload: SchoolExamItemAnalysisIn,
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """补充或修订校考失分小题的错因分类与复盘备注；绝不改写已核对得分与确认状态（INV-04）。"""
    exam = db.get(m.SchoolExam, exam_id)
    if exam is None or exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")
    item = db.get(m.SchoolExamItem, item_id)
    if item is None or item.school_exam_id != exam_id:
        raise HTTPException(404, detail="item not found")
    if item.earned_points >= item.max_points and payload.error_category is not None:
        raise HTTPException(422, detail="FULL_SCORE_ITEM_HAS_NO_ERROR_CATEGORY")
    item.error_category = payload.error_category
    item.error_note = payload.error_note
    db.commit()
    db.refresh(item)
    return _serialize_school_exam_items_with_names(db, exam.subject, [item])[0]


@app.post("/api/school-exams/{exam_id}/items/{item_id}/return-reflection")
def return_school_exam_item_reflection(
    exam_id: str,
    item_id: str,
    payload: AdminReturnReflectionIn,
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """管理端退回学生的校考失分复盘，要求重写；绝不改写已核对得分与知识点（INV-04）。"""
    exam = db.get(m.SchoolExam, exam_id)
    if exam is None or exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")
    item = db.get(m.SchoolExamItem, item_id)
    if item is None or item.school_exam_id != exam_id:
        raise HTTPException(404, detail="item not found")
    if not item.confirmed_by_user:
        raise HTTPException(409, detail="SCHOOL_ITEM_NOT_CONFIRMED")
    if item.earned_points >= item.max_points:
        raise HTTPException(422, detail="FULL_SCORE_ITEM_HAS_NO_ERROR_CATEGORY")
    item.error_note = paper_parser.format_returned_reflection_note(payload.reason, item.error_note)
    item.error_category = None
    db.commit()
    db.refresh(item)
    return _serialize_school_exam_items_with_names(db, exam.subject, [item])[0]


_STEM_CLAIM_TTL = timedelta(minutes=10)


@app.post("/api/school-exams/{exam_id}/extract-stems", response_model=SchoolItemStemExtractOut)
def extract_school_exam_item_stems(
    exam_id: str,
    payload: SchoolItemStemExtractIn | None = None,
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """按需分批抽取校考失分题题干与学生作答（原子认领，逐题仅 AI 解析一次，绝不覆盖已确认）。"""
    exam = db.get(m.SchoolExam, exam_id)
    if exam is None or exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")

    batch_size = payload.batch_size if payload is not None else 3
    now_ts = m.now()
    stale_before = now_ts - _STEM_CLAIM_TTL
    claim_token = f"__claim:{m.uid()[:12]}"

    # 只查 (id, question_label) 元组，避免在 expire_on_commit=False 下污染 Session identity_map
    candidate_rows = db.execute(
        select(m.SchoolExamItem.id, m.SchoolExamItem.question_label).where(
            m.SchoolExamItem.school_exam_id == exam_id,
            m.SchoolExamItem.confirmed_by_user.is_(True),
            m.SchoolExamItem.max_points > 0,
            m.SchoolExamItem.earned_points < m.SchoolExamItem.max_points,
            or_(
                m.SchoolExamItem.stem_state.is_(None),
                (m.SchoolExamItem.stem_state == "extracting") & (m.SchoolExamItem.stem_state_at < stale_before),
            ),
        )
    ).all()
    candidate_rows.sort(key=lambda r: question_label_sort_key(r[1]))
    target_ids = [r[0] for r in candidate_rows[:batch_size]]

    if not target_ids:
        return SchoolItemStemExtractOut(
            requested=0,
            embedded=0,
            vision=0,
            not_found=0,
            remaining_unextracted=0,
            ai_called=False,
        )

    db.execute(
        update(m.SchoolExamItem)
        .where(
            m.SchoolExamItem.id.in_(target_ids),
            or_(
                m.SchoolExamItem.stem_state.is_(None),
                (m.SchoolExamItem.stem_state == "extracting") & (m.SchoolExamItem.stem_state_at < stale_before),
            ),
        )
        .values(stem_state="extracting", stem_source=claim_token, stem_state_at=now_ts)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    db.expire_all()

    claimed = db.execute(
        select(m.SchoolExamItem).where(
            m.SchoolExamItem.school_exam_id == exam_id,
            m.SchoolExamItem.stem_state == "extracting",
            m.SchoolExamItem.stem_source == claim_token,
        )
    ).scalars().all()
    claimed.sort(key=lambda r: question_label_sort_key(r.question_label))

    def _release_claim(rows_to_release: list[m.SchoolExamItem]) -> None:
        release_ids = [r.id for r in rows_to_release]
        if not release_ids:
            return
        db.execute(
            update(m.SchoolExamItem)
            .where(
                m.SchoolExamItem.id.in_(release_ids),
                m.SchoolExamItem.stem_source == claim_token,
            )
            .values(stem_state=None, stem_source=None, stem_state_at=None)
            .execution_options(synchronize_session=False)
        )
        db.commit()
        db.expire_all()

    if not claimed:
        remaining_cnt = db.execute(
            select(func.count()).select_from(m.SchoolExamItem).where(
                m.SchoolExamItem.school_exam_id == exam_id,
                m.SchoolExamItem.confirmed_by_user.is_(True),
                m.SchoolExamItem.max_points > 0,
                m.SchoolExamItem.earned_points < m.SchoolExamItem.max_points,
                m.SchoolExamItem.stem_state.is_(None),
            )
        ).scalar_one()
        return SchoolItemStemExtractOut(
            requested=0,
            embedded=0,
            vision=0,
            not_found=0,
            remaining_unextracted=int(remaining_cnt or 0),
            ai_called=False,
        )

    attachments = db.execute(
        select(m.SchoolPaperAttachment).where(
            m.SchoolPaperAttachment.school_exam_id == exam_id,
            m.SchoolPaperAttachment.owner_id == owner,
        )
    ).scalars().all()
    ordered_atts = sorted(attachments, key=lambda a: (1 if "答题卡" in a.filename else 0, a.created_at, a.id))

    loaded_atts: list[dict] = []
    embedded_by_num: dict[str, str] = {}
    _, nodes, _, _ = _resolve_school_knowledge_meta(db, exam.subject, set())
    for att in ordered_atts:
        try:
            data = files.load_blob(att)
        except Exception:
            continue
        loaded_atts.append(
            {
                "id": att.id,
                "filename": att.filename,
                "media_type": att.media_type,
                "data": data,
            }
        )
        if not embedded_by_num:
            try:
                txt = paper_parser.extract_embedded_text(data, att.media_type)
            except Exception:
                txt = ""
            if txt:
                for parsed in paper_parser.parse_paper_skeleton_from_text(txt, exam.subject, nodes, attachment_id=att.id):
                    m_num = re.search(r"(\d+)", str(parsed.get("question_label") or ""))
                    stem = str(parsed.get("stem") or "").strip()
                    if m_num and stem and m_num.group(1) not in embedded_by_num:
                        embedded_by_num[m_num.group(1)] = stem[:800]

    embedded_count = 0
    remaining: list[m.SchoolExamItem] = []
    for row in claimed:
        m_num = re.search(r"(\d+)", str(row.question_label or ""))
        emb_stem = embedded_by_num.get(m_num.group(1)) if m_num else None
        if emb_stem:
            row.stem_text = emb_stem
            row.stem_state = "embedded_draft"
            row.stem_source = "embedded_text"
            row.stem_state_at = m.now()
            embedded_count += 1
        else:
            remaining.append(row)

    vision_count = 0
    not_found_count = 0
    ai_called = False
    ai_unavailable_reason: str | None = None

    visual_atts = [it for it in loaded_atts if it["media_type"] in ("application/pdf", "image/png", "image/jpeg")]
    if remaining and visual_atts:
        cfg = paper_parser.load_vision_config(require_key=False)
        if cfg is None:
            _release_claim(remaining)
            if embedded_count == 0:
                raise HTTPException(503, detail="VISION_PARSER_NOT_CONFIGURED")
            ai_unavailable_reason = "VISION_PARSER_NOT_CONFIGURED"
        else:
            try:
                ai_called = True
                extracted = paper_parser.extract_lost_item_stems_with_deepseek(
                    subject=exam.subject,
                    attachments=visual_atts,
                    lost_labels=[r.question_label for r in remaining],
                    cfg=cfg,
                )
            except paper_parser.VisionParserUnavailableError as exc:
                logger.warning("extract-stems vision failed exam=%s labels=%s: %s", exam_id, [r.question_label for r in remaining], exc)
                _release_claim(remaining)
                if embedded_count == 0:
                    raise HTTPException(503, detail=str(exc)) from exc
                ai_unavailable_reason = str(exc)
            except Exception as exc:
                logger.exception("extract-stems unexpected failure exam=%s labels=%s", exam_id, [r.question_label for r in remaining])
                _release_claim(remaining)
                if embedded_count == 0:
                    raise HTTPException(500, detail="VISION_PARSER_UNAVAILABLE") from exc
                ai_unavailable_reason = "VISION_PARSER_UNAVAILABLE"
            else:
                for row in remaining:
                    hit = extracted.get(row.question_label)
                    if hit and hit.get("stem_text"):
                        row.stem_text = hit["stem_text"]
                        row.student_answer_text = hit.get("student_answer_text")
                        row.stem_state = "vision_draft"
                        row.stem_source = "vision"
                        row.stem_state_at = m.now()
                        vision_count += 1
                    else:
                        row.stem_state = "not_found"
                        row.stem_source = "vision"
                        row.stem_state_at = m.now()
                        not_found_count += 1
    elif remaining:
        for row in remaining:
            row.stem_state = "not_found"
            row.stem_source = "embedded_text"
            row.stem_state_at = m.now()
            not_found_count += 1

    db.commit()
    remaining_cnt = db.execute(
        select(func.count()).select_from(m.SchoolExamItem).where(
            m.SchoolExamItem.school_exam_id == exam_id,
            m.SchoolExamItem.confirmed_by_user.is_(True),
            m.SchoolExamItem.max_points > 0,
            m.SchoolExamItem.earned_points < m.SchoolExamItem.max_points,
            m.SchoolExamItem.stem_state.is_(None),
        )
    ).scalar_one()
    return SchoolItemStemExtractOut(
        requested=len(claimed),
        embedded=embedded_count,
        vision=vision_count,
        not_found=not_found_count,
        remaining_unextracted=int(remaining_cnt or 0),
        ai_called=ai_called,
        ai_unavailable_reason=ai_unavailable_reason,
    )


@app.patch("/api/school-exams/{exam_id}/items/{item_id}/stem")
def patch_school_exam_item_stem(
    exam_id: str,
    item_id: str,
    payload: SchoolItemStemPatchIn,
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """管理端手工编辑或确认失分题题干与学生作答（不触碰分数与知识点）。"""
    exam = db.get(m.SchoolExam, exam_id)
    if exam is None or exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")
    item = db.get(m.SchoolExamItem, item_id)
    if item is None or item.school_exam_id != exam_id:
        raise HTTPException(404, detail="item not found")
    if not item.confirmed_by_user:
        raise HTTPException(409, detail="SCHOOL_ITEM_NOT_CONFIRMED")
    if item.earned_points >= item.max_points:
        raise HTTPException(422, detail="FULL_SCORE_ITEM_HAS_NO_STEM")

    edited = False
    if "stem_text" in payload.model_fields_set and payload.stem_text != item.stem_text:
        item.stem_text = payload.stem_text
        edited = True
    if "student_answer_text" in payload.model_fields_set and payload.student_answer_text != item.student_answer_text:
        item.student_answer_text = payload.student_answer_text
        edited = True
    if edited:
        item.stem_source = "owner_edited"

    if payload.confirm:
        if not (item.stem_text and item.stem_text.strip()):
            raise HTTPException(422, detail="STEM_TEXT_REQUIRED_TO_CONFIRM")
        item.stem_state = "confirmed"
        item.stem_state_at = m.now()
    elif edited and item.stem_state in (None, "not_found", "extracting"):
        item.stem_state = "vision_draft"
        item.stem_state_at = m.now()

    db.commit()
    db.refresh(item)
    return _serialize_school_exam_items_with_names(db, exam.subject, [item])[0]


@app.post("/api/school-exams/{exam_id}/confirm-stems", response_model=SchoolExamStemsConfirmOut)
def confirm_school_exam_item_stems(
    exam_id: str,
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """管理端批量确认本场所有待核对题干草稿。"""
    exam = db.get(m.SchoolExam, exam_id)
    if exam is None or exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")
    rows = db.execute(
        select(m.SchoolExamItem).where(
            m.SchoolExamItem.school_exam_id == exam_id,
            m.SchoolExamItem.confirmed_by_user.is_(True),
            m.SchoolExamItem.max_points > 0,
            m.SchoolExamItem.earned_points < m.SchoolExamItem.max_points,
            m.SchoolExamItem.stem_state.in_(("embedded_draft", "vision_draft")),
        )
    ).scalars().all()
    confirmed_count = 0
    for row in rows:
        if row.stem_text and row.stem_text.strip():
            row.stem_state = "confirmed"
            row.stem_state_at = m.now()
            confirmed_count += 1
    db.commit()
    return SchoolExamStemsConfirmOut(confirmed_count=confirmed_count)

@app.get("/api/school-exams/{exam_id}/items/{item_id}/coach", response_model=SchoolCoachSessionOut)
def get_admin_school_exam_item_coach(
    exam_id: str,
    item_id: str,
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """管理端第四阶段只读查看学生与书童的校考复盘对话过程（零 AI 调用）。"""
    exam = db.get(m.SchoolExam, exam_id)
    if exam is None or exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")
    item = db.get(m.SchoolExamItem, item_id)
    if item is None or item.school_exam_id != exam_id:
        raise HTTPException(404, detail="item not found")
    session_obj = db.execute(
        select(m.SchoolReflectionCoachSession).where(
            m.SchoolReflectionCoachSession.school_exam_item_id == item_id,
            m.SchoolReflectionCoachSession.learner_id == owner,
        )
    ).scalar_one_or_none()
    return serialize_school_coach_session(db, item_id, session_obj)


@app.delete("/api/school-exams/{exam_id}")
def delete_school_exam(
    exam_id: str,
    confirm: bool = Query(False),
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """删除单场校考及其逐题得分、原卷附件、排名快照；关联扫描试卷解除关联。"""
    exam = db.get(m.SchoolExam, exam_id)
    if exam is None or exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")
    if not confirm:
        raise HTTPException(400, detail="SCHOOL_EXAM_DELETE_CONFIRMATION_REQUIRED")

    attachments = db.execute(
        select(m.SchoolPaperAttachment).where(m.SchoolPaperAttachment.school_exam_id == exam_id)
    ).scalars().all()
    # 先删私有原件；文件删除失败则中止，避免留下数据库孤儿。
    archive_dir = exam.archive_dir
    for attachment in attachments:
        try:
            files.unlink_attachment_blob(attachment)
        except OSError as exc:
            raise HTTPException(409, detail="SCHOOL_EXAM_ATTACHMENT_DELETE_FAILED") from exc

    items = db.execute(
        select(m.SchoolExamItem).where(m.SchoolExamItem.school_exam_id == exam_id)
    ).scalars().all()
    ranks = db.execute(
        select(m.SchoolExamRankSnapshot).where(m.SchoolExamRankSnapshot.school_exam_id == exam_id)
    ).scalars().all()
    papers = db.execute(
        select(m.SchoolExamPaper).where(m.SchoolExamPaper.school_exam_id == exam_id)
    ).scalars().all()
    if archive_dir:
        archive_papers = db.execute(
            select(m.SchoolExamPaper).where(
                m.SchoolExamPaper.learner_id == owner,
                or_(
                    m.SchoolExamPaper.source_ref.like(f"{archive_dir}/%"),
                    m.SchoolExamPaper.source_ref.like(f"%{archive_dir}/%"),
                    m.SchoolExamPaper.relative_path.like(f"{archive_dir}/%"),
                ),
            )
        ).scalars().all()
        seen_paper_ids = {p.id for p in papers}
        for ap in archive_papers:
            if ap.id not in seen_paper_ids:
                papers.append(ap)
                seen_paper_ids.add(ap.id)

    for paper in papers:
        in_archive = bool(archive_dir) and (
            f"{archive_dir}/" in str(paper.source_ref or "")
            or str(getattr(paper, "relative_path", "") or "").startswith(f"{archive_dir}/")
        )
        if in_archive:
            paper_key = paper.storage_key
            paper_rel = getattr(paper, "relative_path", None)
            db.delete(paper)
            db.flush()
            report_pipeline._safe_unlink_unused_blob(db, paper_key, paper_rel)  # noqa: SLF001
        else:
            paper.school_exam_id = None
            paper.status = "needs_review"
            paper.match_state = "NEEDS_REVIEW"
            paper.match_candidates = []
            paper.imported_at = None
            paper.error_code = None
            paper.updated_at = m.now()

    reports = db.execute(
        select(m.SchoolExamReport).where(m.SchoolExamReport.learner_id == owner)
    ).scalars().all()
    for rep in reports:
        links = list(rep.linked_exam_ids or [])
        filtered_links = [lk for lk in links if str(lk.get("exam_id") or "") != exam_id]
        if len(filtered_links) == len(links):
            continue
        if filtered_links:
            rep.linked_exam_ids = filtered_links
        else:
            rep_key = rep.storage_key
            rep_rel = getattr(rep, "relative_path", None)
            rep_cards = db.execute(
                select(m.SchoolExamReportAttachment).where(m.SchoolExamReportAttachment.report_id == rep.id)
            ).scalars().all()
            rep_card_refs = [(c.storage_key, getattr(c, "relative_path", None)) for c in rep_cards]
            for card in rep_cards:
                db.delete(card)
            db.delete(rep)
            db.flush()
            report_pipeline._safe_unlink_unused_blob(db, rep_key, rep_rel)  # noqa: SLF001
            for ck, cr in rep_card_refs:
                report_pipeline._safe_unlink_unused_blob(db, ck, cr)  # noqa: SLF001

    item_ids = [it.id for it in items]
    if item_ids:
        coach_sessions = db.execute(
            select(m.SchoolReflectionCoachSession).where(
                m.SchoolReflectionCoachSession.school_exam_item_id.in_(item_ids)
            )
        ).scalars().all()
        coach_session_ids = [cs.id for cs in coach_sessions]
        if coach_session_ids:
            db.execute(
                delete(m.SchoolReflectionCoachTurn).where(
                    m.SchoolReflectionCoachTurn.session_id.in_(coach_session_ids)
                )
            )
            db.execute(
                delete(m.SchoolReflectionCoachSession).where(
                    m.SchoolReflectionCoachSession.id.in_(coach_session_ids)
                )
            )
    for row in [*items, *attachments, *ranks]:
        db.delete(row)
    db.delete(exam)
    db.flush()
    still_using_archive = (
        bool(archive_dir)
        and db.execute(
            select(m.SchoolExam.id).where(m.SchoolExam.archive_dir == archive_dir).limit(1)
        ).first()
        is not None
    )
    db.commit()
    if archive_dir and not still_using_archive:
        files.remove_school_exam_archive_dir(archive_dir)
    else:
        files.cleanup_empty_school_exam_archive_dir(archive_dir)
    return {
        "deleted": True,
        "id": exam_id,
        "items_deleted": len(items),
        "attachments_deleted": len(attachments),
        "rank_snapshots_deleted": len(ranks),
        "papers_unlinked": len(papers),
    }


def _infer_school_item_subject(question_label: str, knowledge_id: str | None) -> str | None:
    return exam_pipeline.infer_school_item_subject(question_label, knowledge_id)


@app.get("/api/school-exams/{exam_id}/error-analysis", response_model=SchoolExamErrorAnalysisOut)
def get_school_exam_error_analysis(
    exam_id: str,
    subject: SchoolExamSubject | None = Query(default=None),
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """获取单场校考的失分归因、与日常练习掌握度交叉诊断及同科历次顽固失分点对比。"""
    exam = db.get(m.SchoolExam, exam_id)
    if exam is None or exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")
    analysis_subject = subject if (exam.subject == "all" and subject) else exam.subject
    same_subject_exams = db.execute(
        select(m.SchoolExam)
        .where(
            m.SchoolExam.learner_id == owner,
            or_(
                m.SchoolExam.subject == analysis_subject,
                m.SchoolExam.subject == exam.subject,
            ),
        )
        .order_by(m.SchoolExam.exam_date.desc(), m.SchoolExam.created_at.desc(), m.SchoolExam.id.desc())
    ).scalars().all()
    exam_ids = [e.id for e in same_subject_exams]
    all_items = (
        sorted(
            db.execute(
                select(m.SchoolExamItem)
                .where(m.SchoolExamItem.school_exam_id.in_(exam_ids))
            ).scalars().all(),
            key=lambda it: question_label_sort_key(it.question_label),
        )
        if exam_ids
        else []
    )
    if exam.subject == "all" and subject:
        all_items = [
            it
            for it in all_items
            if _infer_school_item_subject(it.question_label, it.knowledge_id) == subject
        ]
    all_kids = {it.knowledge_id for it in all_items}
    has_taxonomy, nodes, name_map, alias_map = _resolve_school_knowledge_meta(db, analysis_subject, all_kids)

    items_by_exam: dict[str, list[dict]] = {eid: [] for eid in exam_ids}
    for it in all_items:
        items_by_exam.setdefault(it.school_exam_id, []).append(
            _serialize_school_exam_item(it, knowledge_name=name_map.get(it.knowledge_id, it.knowledge_id))
        )

    history_payload = [
        {
            "exam_id": e.id,
            "title": e.title,
            "exam_date": str(e.exam_date),
            "earned_points": e.earned_points,
            "max_points": e.max_points,
            "confirmed_by_user": e.confirmed_by_user,
            "items": items_by_exam.get(e.id, []),
        }
        for e in same_subject_exams
    ]

    if has_taxonomy and nodes:
        valid_codes = {n["code"] for n in nodes}
        raw_daily_evidence = get_evidence(db, owner, analysis_subject, include_school_items=False)
        daily_evidence = _get_mapped_evidence(
            db, owner, analysis_subject, valid_codes, include_school_items=False, raw_evidence=raw_daily_evidence
        )
        practice_mastery = compute_knowledge_mastery(nodes, daily_evidence)
        # 兼容仅出现在基础合成测试/历史旧编码、未映射进 2022 候选集的日常作答考点
        extra_kids = sorted({ev.knowledge_id for ev in raw_daily_evidence} - valid_codes)
        if extra_kids:
            practice_mastery.extend(
                compute_knowledge_mastery(
                    [{"code": k, "name": k, "is_elective": False} for k in extra_kids],
                    raw_daily_evidence,
                )
            )
    else:
        practice_mastery = []

    exam_earned = exam.earned_points
    exam_max = exam.max_points
    exam_confirmed = exam.confirmed_by_user
    if exam.subject == "all" and subject:
        for rep in db.execute(
            select(m.SchoolExamReport).where(m.SchoolExamReport.learner_id == owner)
        ).scalars().all():
            if any(isinstance(lnk, dict) and lnk.get("exam_id") == exam.id for lnk in (rep.linked_exam_ids or [])):
                s_entry = next(
                    (s for s in (rep.subjects or []) if isinstance(s, dict) and s.get("subject") == subject),
                    None,
                )
                if s_entry is not None:
                    if s_entry.get("score") is not None:
                        exam_earned = float(s_entry["score"])
                    if s_entry.get("max_score") is not None:
                        exam_max = float(s_entry["max_score"])
                    exam_confirmed = bool(s_entry.get("confirmed_by_user"))
                break

    return analyze_school_exam_errors(
        exam_meta={
            "id": exam.id,
            "subject": analysis_subject,
            "title": exam.title,
            "exam_date": str(exam.exam_date),
            "earned_points": exam_earned,
            "max_points": exam_max,
            "confirmed_by_user": exam_confirmed,
        },
        exam_items=items_by_exam.get(exam.id, []),
        history_exams=history_payload,
        practice_mastery=practice_mastery,
        has_taxonomy=has_taxonomy,
        knowledge_alias_map=alias_map,
    )

@app.get("/api/school-exams/{exam_id}")
def get_school_exam_detail(exam_id: str, owner: str = Depends(require_admin), db: Session = Depends(get_db)):
    """考试详情 + 逐题得分（含确认状态与错因备注）+ 附件元数据；存储键绝不进响应（AC-SEC-01）。"""
    exam = db.get(m.SchoolExam, exam_id)
    if exam is None or exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")
    items = sorted(
        db.execute(select(m.SchoolExamItem).where(m.SchoolExamItem.school_exam_id == exam.id)).scalars().all(),
        key=lambda it: question_label_sort_key(it.question_label),
    )
    attachments = db.execute(select(m.SchoolPaperAttachment).where(m.SchoolPaperAttachment.school_exam_id == exam.id, m.SchoolPaperAttachment.owner_id == owner).order_by(m.SchoolPaperAttachment.created_at, m.SchoolPaperAttachment.id)).scalars().all()
    return {"id": exam.id, "subject": exam.subject, "title": exam.title, "exam_date": str(exam.exam_date),
            "earned_points": exam.earned_points, "max_points": exam.max_points, "confirmed_by_user": exam.confirmed_by_user,
            "school_name": exam.school_name, "grade": exam.grade, "exam_type": exam.exam_type,
            "exam_type_label": exam.exam_type_label,
            "academic_year": exam.academic_year, "term": exam.term, "series_title": exam.series_title,
            "external_exam_id": exam.external_exam_id, "source_kind": exam.source_kind,
            "class_highest": exam.class_highest, "grade_highest": exam.grade_highest,
            "items": _serialize_school_exam_items_with_names(db, exam.subject, items),
            "attachments": [
                {
                    "id": a.id,
                    "filename": a.filename,
                    "media_type": a.media_type,
                    "sha256": a.sha256,
                    "byte_size": a.byte_size,
                    "category": getattr(a, "category", "exam_paper"),
                    "created_at": a.created_at,
                }
                for a in attachments
            ]}


def save_school_paper(
    db,
    exam_id,
    owner,
    filename,
    media_type,
    data,
    expected_sha256,
    *,
    category: str = "exam_paper",
    archive_dir_override: str | None = None,
):
    exam = db.get(m.SchoolExam, exam_id)
    if exam is None or exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")
    files.validate_file(data, media_type)
    digest = sha256(data).hexdigest()
    if expected_sha256 is not None and expected_sha256 != digest:
        raise HTTPException(422, detail="UPLOAD_HASH_MISMATCH")
    archive_dir = (archive_dir_override or "").strip() or (exam.archive_dir or "").strip()
    if not archive_dir:
        archive_dir = build_school_exam_archive_dir_name(exam.exam_date, exam.title, exam.id)
        exam.archive_dir = archive_dir
    elif not exam.archive_dir:
        exam.archive_dir = archive_dir
    subdir = "answer-sheet" if category == "answer_sheet" else "exam-paper"
    key = None
    rel_path = None
    try:
        key, rel_path = files.write_school_exam_file(archive_dir, subdir, filename, data)
        attachment = m.SchoolPaperAttachment(
            school_exam_id=exam.id,
            owner_id=owner,
            filename=filename,
            media_type=media_type,
            sha256=digest,
            byte_size=len(data),
            storage_key=key,
            category=category,
            relative_path=rel_path,
        )
        db.add(attachment)
        db.commit()
    except (OSError, SQLAlchemyError, HomeIdentityError):
        db.rollback()
        if rel_path is not None:
            try:
                files.school_exam_file_path(rel_path).unlink(missing_ok=True)
            except Exception:
                pass
        raise HTTPException(503, detail="ATTACHMENT_STORAGE_UNAVAILABLE")
    db.refresh(attachment)
    return {"id": attachment.id, "filename": attachment.filename, "media_type": attachment.media_type,
            "sha256": attachment.sha256, "byte_size": attachment.byte_size, "created_at": attachment.created_at}

@app.post("/api/school-exams/{exam_id}/paper", status_code=201,
          openapi_extra={"requestBody": {"required": True, "content": {
              media: {"schema": {"type": "string", "format": "binary"}} for media in files.MEDIA_TYPES}}})
async def upload_school_paper(exam_id: str, request: Request,
                              filename: str = Query(min_length=1, max_length=255, pattern=r"^[^/\\\x00-\x1f\x7f]+$"),
                              expected_sha256: str | None = Query(default=None, pattern="^[0-9a-f]{64}$"),
                              owner: str = Depends(require_admin), db: Session = Depends(get_db)):
    """原始二进制请求体；上限 10 MiB，落私有目录；不存在任何读取附件字节的端点（AC-SEC-01）。"""
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type not in files.MEDIA_TYPES:
        raise HTTPException(415, detail="UNSUPPORTED_FILE_TYPE")
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > files.MAX_BYTES:
            raise HTTPException(413, detail="INVALID_FILE_SIZE")
        data.extend(chunk)
    return await run_in_threadpool(save_school_paper, db, exam_id, owner, filename, media_type, bytes(data), expected_sha256)

@app.post("/api/goals", status_code=201)
def set_goal(payload: GoalIn, student: str = Depends(require_student), db: Session = Depends(get_db)):
    owner = student
    next_version = (db.scalar(select(func.max(m.Goal.version)).where(m.Goal.learner_id == owner, m.Goal.subject == payload.subject)) or 0) + 1
    g = m.Goal(learner_id=owner, version=next_version, **payload.model_dump())
    db.add(g); db.commit(); db.refresh(g)
    return {"id": g.id, "version": g.version, "status": "recorded"}

@app.get("/api/guidance/profile")
def profile(subject: Subject, student: str = Depends(require_student), db: Session = Depends(get_db)):
    raw_knowledge = summarize(get_evidence(db, student, subject))
    student_knowledge = [
        {
            "topic": get_topic_label(item["knowledge_id"]),
            "sample_size": item["sample_size"],
            "observed_rate": item["observed_rate"],
            "evidence_status": item["evidence_status"],
        }
        for item in raw_knowledge
    ]
    return {"subject": subject, "model_version": MODEL_VERSION, "knowledge": student_knowledge, "score_prediction": None, "school_exam_scores_are_not_equated": True}

@app.get("/api/guidance/plan")
def plan(subject: Subject, student: str = Depends(require_student), db: Session = Depends(get_db)):
    goal = db.execute(select(m.Goal).where(m.Goal.learner_id == student, m.Goal.subject == subject).order_by(m.Goal.version.desc())).scalars().first()
    if goal is None:
        raise HTTPException(409, detail="GOAL_REQUIRED")
    knowledge = [x[0] for x in db.execute(select(m.QuestionVersion.knowledge_ids).join(m.Question).where(m.Question.subject == subject, m.QuestionVersion.status == "published")).all()]
    # knowledge above is a list of JSON lists; flatten without assuming a fixed taxonomy.
    known_ids = sorted({kid for item in knowledge for kid in item})
    raw_evidence = summarize(get_evidence(db, student, subject))
    evidence_map = {item["knowledge_id"]: item for item in raw_evidence}
    result = make_plan(raw_evidence, goal.target_points, goal.max_points, goal.minutes_per_day, known_ids)

    student_steps = []
    for s in result["steps"]:
        kid = s["knowledge_id"]
        topic = get_topic_label(kid)
        sample_size = evidence_map.get(kid, {}).get("sample_size", 0)
        observed = s.get("observed_rate")
        advice = get_student_advice(s["gap_type"], topic, observed, result["planning_threshold"])
        step_dict = {
            "topic": topic,
            "gap_type": s["gap_type"],
            "action": s["action"],
            "reason": s["reason"],
            "advice": advice,
            "priority": s["priority"],
            "sample_size": sample_size,
        }
        if observed is not None:
            step_dict["observed_rate"] = observed
        student_steps.append(step_dict)

    return {
        "subject": subject,
        "goal_version": goal.version,
        "model_version": result["model_version"],
        "target_mapping_status": result["target_mapping_status"],
        "planning_threshold": result["planning_threshold"],
        "minutes_per_day": result["minutes_per_day"],
        "steps": student_steps,
        "disclaimer": result["disclaimer"],
    }

@app.get("/api/practice/resume")
def resume_item(subject: Subject, student: str = Depends(require_student), db: Session = Depends(get_db)):
    """恢复本科目最近一个未作答的**诊断**曝光（iPad 刷新/重开/切后台后会话可续，未见题不空烧）。
    只读：不新建曝光、不改写历史；该曝光若已作答（或不存在）即返回 item=null。
    仅限 purpose=evaluation：训练取题无状态成本（轮换本身合规），诊断未见题才是稀缺资源。"""
    owner = student
    exp = db.execute(select(m.Exposure)
                     .join(m.QuestionVersion, m.QuestionVersion.id == m.Exposure.question_version_id)
                     .join(m.Question, m.Question.id == m.QuestionVersion.question_id)
                     .where(m.Exposure.learner_id == owner, m.Exposure.purpose == "evaluation", m.Question.subject == subject)
                     .order_by(m.Exposure.shown_at.desc(), m.Exposure.id.desc())).scalars().first()
    if exp is None:
        return {"item": None}
    answered = db.scalar(select(m.AnswerAttempt.id).where(m.AnswerAttempt.exposure_id == exp.id).limit(1)) is not None
    if answered:
        return {"item": None}
    v = db.get(m.QuestionVersion, exp.question_version_id)
    return {"item": {"exposure_id": exp.id, "question_version_id": v.id, "purpose": exp.purpose,
                     "unseen_at_exposure": exp.is_unseen_at_exposure, "stem": v.stem, "kind": v.kind,
                     "group_context": v.group_context, "media_attachment_id": v.media_attachment_id,
                     "options": v.options, "max_points": v.max_points, "subject": subject}}

@app.get("/api/guidance/pool-health")
def pool_health_endpoint(subject: Subject, owner: str = Depends(require_admin), db: Session = Depends(get_db)):
    """题池体检（管理员专属）：按逻辑题的最新已发布版与 owner 曝光记录如实计数（训练轮换与诊断余量）。
    查询形状刻意与 next_item 一致（最新发布版子查询），不引入第二套选题口径。"""
    latest = select(m.QuestionVersion.question_id, func.max(m.QuestionVersion.version).label("version")).where(m.QuestionVersion.status == "published").group_by(m.QuestionVersion.question_id).subquery()
    versions = db.execute(select(m.QuestionVersion).join(m.Question).join(latest, (m.QuestionVersion.question_id == latest.c.question_id) & (m.QuestionVersion.version == latest.c.version)).where(m.Question.subject == subject, m.QuestionVersion.status == "published")).scalars().all()
    counts = dict(db.execute(select(m.Exposure.question_id, func.count()).where(m.Exposure.learner_id == owner).group_by(m.Exposure.question_id)).all())
    entries = [{"question_id": v.question_id, "knowledge_id": kid, "seen": counts.get(v.question_id, 0) > 0}
               for v in versions for kid in (v.knowledge_ids or [])]
    return {"subject": subject, **pool_health(entries)}

@app.get("/api/guidance/validation")
def validation(subject: Subject, student: str = Depends(require_student), db: Session = Depends(get_db)):
    """独立未见题复测的可观察对比；不可比或证据不足绝不宣称涨分。学生端响应移除内部知识点编号。"""
    owner = student
    rows = db.execute(select(m.AnswerAttempt, m.QuestionVersion).join(m.Exposure, m.Exposure.id == m.AnswerAttempt.exposure_id).join(m.QuestionVersion, m.QuestionVersion.id == m.AnswerAttempt.question_version_id).join(m.Question, m.Question.id == m.QuestionVersion.question_id).where(m.AnswerAttempt.learner_id == owner, m.Question.subject == subject, m.Exposure.purpose == "evaluation", m.Exposure.is_unseen_at_exposure.is_(True), m.AnswerAttempt.hints_used.is_(False), m.AnswerAttempt.earned_points.is_not(None), m.AnswerAttempt.scoring_origin == "reviewed_answer_key").order_by(m.AnswerAttempt.created_at, m.AnswerAttempt.id)).all()
    per_kid: dict[str, dict[str, Evidence]] = {}
    for a, v in rows:
        if len(v.knowledge_ids) != 1:
            continue
        # 装配侧已保证独立未见单考点；去重属防御性（ST-004 已保证每版本至多一条 evaluation 作答）。
        per_kid.setdefault(v.knowledge_ids[0], {}).setdefault(v.id, Evidence(source_event_id=a.id, question_version_id=v.id, knowledge_id=v.knowledge_ids[0], earned_points=a.earned_points, max_points=a.max_points, independent=True, is_first_exposure=True))
    baseline, retest = [], []
    for kid in sorted(per_kid):
        items = list(per_kid[kid].values())
        baseline.extend(items[:MIN_DISTINCT_ITEMS])
        retest.extend(items[MIN_DISTINCT_ITEMS:])
    raw_val = compare_validation(baseline, retest)
    student_knowledge = []
    for item in raw_val["knowledge"]:
        entry = {
            "topic": get_topic_label(item["knowledge_id"]),
            "verdict": item["verdict"],
            "baseline_items": item["baseline_items"],
            "retest_items": item["retest_items"],
        }
        if "baseline_rate" in item:
            entry["baseline_rate"] = item["baseline_rate"]
        if "retest_rate" in item:
            entry["retest_rate"] = item["retest_rate"]
        if "reason" in item:
            entry["reason"] = item["reason"]
        student_knowledge.append(entry)
    return {
        "subject": subject,
        "model_version": raw_val["model_version"],
        "verdict": raw_val["verdict"],
        "comparable": raw_val["comparable"],
        "score_prediction": raw_val["score_prediction"],
        "knowledge": student_knowledge,
        "disclaimer": raw_val["disclaimer"],
    }
