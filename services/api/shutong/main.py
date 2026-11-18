"""Private API foundation. Read CODEX_START_HERE.md before extending."""
from __future__ import annotations
import os
import re
from datetime import datetime, timezone
from hashlib import sha256
from fastapi import FastAPI, Depends, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import delete, select, func, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from .auth import require_admin, require_student, require_owner
from .topic_labels import get_topic_label, get_student_advice, TAXONOMY_MAP, SYNTHETIC_MAP
from .taxonomy_bridge import resolve_question_to_candidate_codes
from .content import create_question_draft
from .ingestion import router as ingestion_router, require_import_integrity
from .fourcorpus import router as corpus_router
from .learning_api import router as learning_router, get_evidence, _load_effective_knowledge_nodes, _get_mapped_evidence
from .research import official_reject_reason
from .database import get_db
from .home import HomeIdentityError
from . import models as m
from . import private_files as files
from . import school_paper_parser as paper_parser
from . import k12100_backfill
from . import k12100_report_sync
from . import school_exam_pipeline as exam_pipeline
from . import school_report_pipeline as report_pipeline
from .schemas import SourceIn, QuestionIn, QuestionRevisionOut, AttemptIn, SelfAssessmentIn, SchoolExamIn, SchoolExamConfirmIn, SchoolExamItemsIn, SchoolExamItemAnalysisIn, SchoolExamErrorAnalysisOut, SchoolItemConfirmIn, SchoolItemConfirmBatchIn, SchoolExamParseDraftsIn, SchoolExamSyncDraftsIn, K12100SyncJobStartIn, K12100ImportBundleIn, K12100ReportJobStartIn, SchoolPaperScanIn, SchoolPaperMatchIn, SchoolPaperCollectIn, SchoolExamRankConfirmIn, SchoolExamReportConfirmIn, SchoolExamReportPatchIn, SchoolExamReportSubjectIn, GoalIn, Subject, SchoolExamSubject
from .guidance import Evidence, MODEL_VERSION, summarize, make_plan, compare_validation, pool_health, compute_knowledge_mastery, analyze_school_exam_errors, MIN_DISTINCT_ITEMS

app = FastAPI(title="书童 ShuTong API", version="0.1.0", docs_url=None, redoc_url=None)
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
    db.add(record); db.commit(); db.refresh(record)
    return {"id": record.id, "status": "user_confirmed" if record.confirmed_by_user else "unconfirmed", "knowledge_evidence_created": False}

@app.get("/api/school-exams")
def get_school_exams(subject: SchoolExamSubject, owner: str = Depends(require_admin), db: Session = Depends(get_db)):
    exams = db.execute(select(m.SchoolExam).where(m.SchoolExam.learner_id == owner, m.SchoolExam.subject == subject).order_by(m.SchoolExam.exam_date.desc())).scalars().all()
    return [{"id": e.id, "title": e.title, "exam_date": str(e.exam_date), "earned_points": e.earned_points, "max_points": e.max_points, "confirmed_by_user": e.confirmed_by_user,
             "school_name": e.school_name, "grade": e.grade, "exam_type": e.exam_type, "exam_type_label": e.exam_type_label,
             "academic_year": e.academic_year, "term": e.term, "series_title": e.series_title,
             "external_exam_id": e.external_exam_id, "source_kind": e.source_kind} for e in exams]

@app.post("/api/school-exams/{exam_id}/confirm")
def confirm_school_exam(exam_id: str, payload: SchoolExamConfirmIn, owner: str = Depends(require_admin), db: Session = Depends(get_db)):
    """待核对校考总分的人工补充与确认；确认后不可变，且永不产生考点证据（INV-05）。"""
    exam = db.get(m.SchoolExam, exam_id)
    if exam is None or exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")
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


def _serialize_school_exam_item(i: m.SchoolExamItem, knowledge_name: str | None = None) -> dict:
    """统一序列化校考逐题明细（含失分、结构化错因与自动解析草稿元数据）。"""
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
        "draft_source_attachment_id": i.draft_source_attachment_id,
        "draft_confidence": i.draft_confidence,
        "draft_reason": i.draft_reason,
        "draft_knowledge_candidates": i.draft_knowledge_candidates,
    }
    if knowledge_name is not None:
        out["knowledge_name"] = knowledge_name
    return out


def _serialize_school_exam_items_with_names(
    db: Session, subject: str, items: list[m.SchoolExamItem]
) -> list[dict]:
    """批量附带课标知识点中文名称序列化校考逐题记录。"""
    if not items:
        return []
    _, _, name_map, _ = _resolve_school_knowledge_meta(db, subject, {it.knowledge_id for it in items})
    return [_serialize_school_exam_item(it, knowledge_name=name_map.get(it.knowledge_id, it.knowledge_id)) for it in items]


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

    _, knowledge_catalog, _, _ = _resolve_school_knowledge_meta(db, exam.subject, set())
    loaded = [
        {
            "id": att.id,
            "filename": att.filename,
            "media_type": att.media_type,
            "data": files.load_blob(att),
        }
        for att in attachments
    ]

    def _collect_skeleton() -> list[dict]:
        combined: list[dict] = []
        seen_lbls: set[str] = set()
        for item in loaded:
            text = paper_parser.extract_embedded_text(item["data"], item["media_type"])
            if not text:
                continue
            for row in paper_parser.parse_paper_skeleton_from_text(
                text, exam.subject, knowledge_catalog, attachment_id=item["id"]
            ):
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
            try:
                draft_items, meta = paper_parser.parse_items_with_deepseek_vision(
                    subject=exam.subject,
                    knowledge_catalog=knowledge_catalog,
                    attachments=visual_attachments,
                    mask_student_header=payload.mask_student_header,
                    cfg=cfg,
                )
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
def get_school_exam_sync_center(owner: str = Depends(require_admin), db: Session = Depends(get_db)):
    """返回四步同步中心的真实后端状态：卷源、扫描、试卷与严格匹配候选。"""
    try:
        return exam_pipeline.get_sync_center(db, owner=owner)
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


def _auto_map_report_items(db: Session, report: m.SchoolExamReport) -> int:
    """用已归档原卷文字层做本地知识点匹配，只填候选，不确认。"""
    links = {str(link.get("subject")): str(link.get("exam_id")) for link in (report.linked_exam_ids or [])}
    applied = 0
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
            continue
        skeleton = paper_parser.parse_paper_skeleton_from_text(text, subject, nodes)
        by_number: dict[str, dict] = {}
        for item in skeleton:
            match = re.search(r"(\d+)", str(item.get("question_label") or ""))
            if match:
                by_number[match.group(1)] = item
        rows = db.execute(
            select(m.SchoolExamItem).where(m.SchoolExamItem.school_exam_id == exam_id)
        ).scalars().all()
        for row in rows:
            if row.confirmed_by_user or row.knowledge_id != "unmapped":
                continue
            match = re.search(r"(\d+)", row.question_label)
            candidate = by_number.get(match.group(1)) if match else None
            if not candidate:
                continue
            children = candidate.get("draft_knowledge_candidates") or []
            knowledge_id = str(candidate.get("knowledge_id") or "")
            if not children or knowledge_id in {"", "unmapped"}:
                continue
            if all("未命中明确关键词" in str(child.get("reason") or "") for child in children):
                continue
            row.knowledge_id = knowledge_id
            row.draft_knowledge_candidates = children
            row.draft_confidence = "auto_matched"
            applied += 1
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
        data = files.blob_path(attachment.storage_key).read_bytes()
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
    """扫描当前环境 0700 私有收件箱；所有论文先待核对，逐题仍走既有 ocr_draft 门禁。"""
    try:
        return exam_pipeline.scan_local_papers(
            db,
            owner=owner,
            apply_imports=bool(payload and payload.apply_imports),
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
    )

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
    for attachment in attachments:
        try:
            files.blob_path(attachment.storage_key).unlink(missing_ok=True)
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
    for paper in papers:
        paper.school_exam_id = None
        paper.status = "needs_review"
        paper.match_state = "NEEDS_REVIEW"
        paper.match_candidates = []
        paper.imported_at = None
        paper.error_code = None
        paper.updated_at = m.now()
    for row in [*items, *attachments, *ranks]:
        db.delete(row)
    db.delete(exam)
    db.commit()
    return {
        "deleted": True,
        "id": exam_id,
        "items_deleted": len(items),
        "attachments_deleted": len(attachments),
        "rank_snapshots_deleted": len(ranks),
        "papers_unlinked": len(papers),
    }


@app.get("/api/school-exams/{exam_id}/error-analysis", response_model=SchoolExamErrorAnalysisOut)
def get_school_exam_error_analysis(
    exam_id: str,
    owner: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """获取单场校考的失分归因、与日常练习掌握度交叉诊断及同科历次顽固失分点对比。"""
    exam = db.get(m.SchoolExam, exam_id)
    if exam is None or exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")
    same_subject_exams = db.execute(
        select(m.SchoolExam)
        .where(m.SchoolExam.learner_id == owner, m.SchoolExam.subject == exam.subject)
        .order_by(m.SchoolExam.exam_date.desc(), m.SchoolExam.created_at.desc(), m.SchoolExam.id.desc())
    ).scalars().all()
    exam_ids = [e.id for e in same_subject_exams]
    all_items = (
        db.execute(
            select(m.SchoolExamItem)
            .where(m.SchoolExamItem.school_exam_id.in_(exam_ids))
            .order_by(m.SchoolExamItem.question_label)
        ).scalars().all()
        if exam_ids
        else []
    )
    all_kids = {it.knowledge_id for it in all_items}
    has_taxonomy, nodes, name_map, alias_map = _resolve_school_knowledge_meta(db, exam.subject, all_kids)

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
        raw_daily_evidence = get_evidence(db, owner, exam.subject, include_school_items=False)
        daily_evidence = _get_mapped_evidence(
            db, owner, exam.subject, valid_codes, include_school_items=False, raw_evidence=raw_daily_evidence
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

    return analyze_school_exam_errors(
        exam_meta={
            "id": exam.id,
            "subject": exam.subject,
            "title": exam.title,
            "exam_date": str(exam.exam_date),
            "earned_points": exam.earned_points,
            "max_points": exam.max_points,
            "confirmed_by_user": exam.confirmed_by_user,
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
    items = db.execute(select(m.SchoolExamItem).where(m.SchoolExamItem.school_exam_id == exam.id).order_by(m.SchoolExamItem.question_label)).scalars().all()
    attachments = db.execute(select(m.SchoolPaperAttachment).where(m.SchoolPaperAttachment.school_exam_id == exam.id, m.SchoolPaperAttachment.owner_id == owner).order_by(m.SchoolPaperAttachment.created_at, m.SchoolPaperAttachment.id)).scalars().all()
    return {"id": exam.id, "subject": exam.subject, "title": exam.title, "exam_date": str(exam.exam_date),
            "earned_points": exam.earned_points, "max_points": exam.max_points, "confirmed_by_user": exam.confirmed_by_user,
            "school_name": exam.school_name, "grade": exam.grade, "exam_type": exam.exam_type,
            "exam_type_label": exam.exam_type_label,
            "academic_year": exam.academic_year, "term": exam.term, "series_title": exam.series_title,
            "external_exam_id": exam.external_exam_id, "source_kind": exam.source_kind,
            "class_highest": exam.class_highest, "grade_highest": exam.grade_highest,
            "items": _serialize_school_exam_items_with_names(db, exam.subject, items),
            "attachments": [{"id": a.id, "filename": a.filename, "media_type": a.media_type, "sha256": a.sha256,
                             "byte_size": a.byte_size, "created_at": a.created_at} for a in attachments]}

def save_school_paper(db, exam_id, owner, filename, media_type, data, expected_sha256):
    exam = db.get(m.SchoolExam, exam_id)
    if exam is None or exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")
    files.validate_file(data, media_type)
    digest = sha256(data).hexdigest()
    if expected_sha256 is not None and expected_sha256 != digest:
        raise HTTPException(422, detail="UPLOAD_HASH_MISMATCH")
    key = None
    try:
        key = files.write_blob(data)
        attachment = m.SchoolPaperAttachment(school_exam_id=exam.id, owner_id=owner, filename=filename,
                                            media_type=media_type, sha256=digest, byte_size=len(data), storage_key=key)
        db.add(attachment)
        db.commit()
    except (OSError, SQLAlchemyError):
        db.rollback()
        if key is not None:
            files.blob_path(key).unlink(missing_ok=True)
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
