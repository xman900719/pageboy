"""Private API foundation. Read CODEX_START_HERE.md before extending."""
from __future__ import annotations
import os
from datetime import datetime, timezone
from hashlib import sha256
from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from .auth import require_owner
from .content import create_question_draft
from .ingestion import router as ingestion_router, require_import_integrity
from .database import get_db
from . import models as m
from . import private_files as files
from .schemas import SourceIn, QuestionIn, QuestionRevisionOut, AttemptIn, SelfAssessmentIn, SchoolExamIn, SchoolExamItemsIn, SchoolItemConfirmIn, GoalIn, Subject
from .guidance import Evidence, MODEL_VERSION, summarize, make_plan, compare_validation, pool_health, MIN_DISTINCT_ITEMS

app = FastAPI(title="书童 ShuTong API", version="0.1.0", docs_url=None, redoc_url=None)
app.include_router(ingestion_router)
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if x.strip()], allow_credentials=False, allow_methods=["GET","POST"], allow_headers=["Authorization", "Content-Type"])

@app.get("/health/live")
def live():
    # app_revision 供部署/回滚演练核对“哪个构建在服务”（ST-017）；未设置时如实报 dev。
    return {"status": "alive", "app_revision": os.getenv("SHUTONG_APP_REVISION", "dev")}

@app.get("/health/ready")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(503, detail="database unavailable")
    return {"status": "ready"}

@app.post("/api/admin/sources", status_code=201)
def add_source(payload: SourceIn, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
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
def subjects(owner: str = Depends(require_owner)):
    return ["math", "chinese", "english", "physics"]

@app.get("/api/practice/next")
def next_item(subject: Subject, purpose: str = Query(default="training", pattern="^(training|evaluation)$"), knowledge_id: str | None = None, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    """A returned question is immediately recorded as exposed. Evaluation requires unseen item."""
    # 按逻辑题选择最新已发布版，较新的草稿不替代当前发布版。
    latest = select(m.QuestionVersion.question_id, func.max(m.QuestionVersion.version).label("version")).where(m.QuestionVersion.status == "published").group_by(m.QuestionVersion.question_id).subquery()
    versions = db.execute(select(m.QuestionVersion).join(m.Question).join(latest, (m.QuestionVersion.question_id == latest.c.question_id) & (m.QuestionVersion.version == latest.c.version)).where(m.Question.subject == subject, m.QuestionVersion.status == "published").order_by(m.QuestionVersion.created_at, m.QuestionVersion.id)).scalars().all()
    candidates = [v for v in versions if not knowledge_id or knowledge_id in v.knowledge_ids]
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
        return {"exposure_id": exp.id, "question_version_id": v.id, "purpose": purpose, "unseen_at_exposure": exp.is_unseen_at_exposure, "stem": v.stem, "kind": v.kind, "group_context": v.group_context, "media_attachment_id": v.media_attachment_id, "options": v.options, "max_points": v.max_points, "subject": subject, "knowledge_ids": v.knowledge_ids}
    raise HTTPException(404, detail="NO_ELIGIBLE_QUESTION")

@app.post("/api/practice/attempts", status_code=201)
def submit_attempt(payload: AttemptIn, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
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
def attempt_reference(attempt_id: str, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    """主观题参考答案：作答先行才可对答案（以 attempt 存在为门）；非主观不适用。"""
    attempt = db.get(m.AnswerAttempt, attempt_id)
    if attempt is None or attempt.learner_id != owner:
        raise HTTPException(404, detail="attempt not found")
    version = db.get(m.QuestionVersion, attempt.question_version_id)
    if version.kind != "subjective":
        raise HTTPException(409, detail="REFERENCE_NOT_APPLICABLE")
    return {"reference_answer": version.correct_answer, "max_points": version.max_points}

@app.post("/api/practice/attempts/{attempt_id}/self-assessment", status_code=201)
def record_self_assessment(attempt_id: str, payload: SelfAssessmentIn, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    """主观自评为独立来源记录：不改写作答行，一次自评不可更新（INV-04），不进客观证据。"""
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
def list_attempts(subject: Subject, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    """评分来源溯源列表：作答行 origin 与自评记录并列可审计；自评不进 get_evidence/profile。"""
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
def add_school_exam(payload: SchoolExamIn, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    record = m.SchoolExam(learner_id=owner, **payload.model_dump())
    db.add(record); db.commit(); db.refresh(record)
    return {"id": record.id, "status": "user_confirmed" if record.confirmed_by_user else "unconfirmed", "knowledge_evidence_created": False}

@app.get("/api/school-exams")
def get_school_exams(subject: Subject, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    exams = db.execute(select(m.SchoolExam).where(m.SchoolExam.learner_id == owner, m.SchoolExam.subject == subject).order_by(m.SchoolExam.exam_date.desc())).scalars().all()
    return [{"id": e.id, "title": e.title, "exam_date": str(e.exam_date), "earned_points": e.earned_points, "max_points": e.max_points, "confirmed_by_user": e.confirmed_by_user} for e in exams]

@app.post("/api/school-exams/{exam_id}/items", status_code=201)
def add_school_exam_items(exam_id: str, payload: SchoolExamItemsIn, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
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
        record = m.SchoolExamItem(school_exam_id=exam.id, question_label=item.question_label,
                                   knowledge_id=item.knowledge_id, earned_points=item.earned_points,
                                   max_points=item.max_points, scoring_origin=item.scoring_origin,
                                   confirmed_by_user=confirmed, confirmed_at=m.now() if confirmed else None)
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
    return {"items": [{"id": r.id, "question_label": r.question_label, "scoring_origin": r.scoring_origin, "confirmed_by_user": r.confirmed_by_user} for r in records],
            "evidence_created": sum(1 for r in records if r.confirmed_by_user)}

@app.post("/api/school-exams/{exam_id}/items/{item_id}/confirm")
def confirm_school_exam_item(exam_id: str, item_id: str, payload: SchoolItemConfirmIn, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    """仅 ocr_draft 草稿可人工确认（可修正识别分）；确认后不可变（INV-04，改判须另建记录）。"""
    exam = db.get(m.SchoolExam, exam_id)
    if exam is None or exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")
    item = db.get(m.SchoolExamItem, item_id)
    if item is None or item.school_exam_id != exam_id:
        raise HTTPException(404, detail="item not found")
    if item.confirmed_by_user:
        if payload.earned_points == item.earned_points:
            raise HTTPException(409, detail="SCHOOL_ITEM_ALREADY_CONFIRMED")
        raise HTTPException(409, detail="SCHOOL_ITEM_IMMUTABLE")
    if item.scoring_origin != "ocr_draft":
        # 经 API 不可达（manual_entry 建即确认）：防御绕过应用层、直改库产生的越界行，使其仍需人工裁决。
        raise HTTPException(409, detail="SCHOOL_ITEM_ALREADY_CONFIRMED")
    if payload.earned_points > item.max_points:
        raise HTTPException(422, detail="earned_points exceeds max_points")
    item.earned_points = payload.earned_points
    item.confirmed_by_user = True
    item.confirmed_at = m.now()
    db.commit()
    return {"id": item.id, "question_label": item.question_label, "earned_points": item.earned_points,
            "max_points": item.max_points, "scoring_origin": item.scoring_origin, "confirmed_by_user": item.confirmed_by_user}

@app.get("/api/school-exams/{exam_id}")
def get_school_exam_detail(exam_id: str, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    """考试详情 + 逐题得分（含确认状态）+ 附件元数据；存储键绝不进响应（AC-SEC-01）。"""
    exam = db.get(m.SchoolExam, exam_id)
    if exam is None or exam.learner_id != owner:
        raise HTTPException(404, detail="exam not found")
    items = db.execute(select(m.SchoolExamItem).where(m.SchoolExamItem.school_exam_id == exam.id).order_by(m.SchoolExamItem.question_label)).scalars().all()
    attachments = db.execute(select(m.SchoolPaperAttachment).where(m.SchoolPaperAttachment.school_exam_id == exam.id, m.SchoolPaperAttachment.owner_id == owner).order_by(m.SchoolPaperAttachment.created_at, m.SchoolPaperAttachment.id)).scalars().all()
    return {"id": exam.id, "subject": exam.subject, "title": exam.title, "exam_date": str(exam.exam_date),
            "earned_points": exam.earned_points, "max_points": exam.max_points, "confirmed_by_user": exam.confirmed_by_user,
            "items": [{"id": i.id, "question_label": i.question_label, "knowledge_id": i.knowledge_id,
                       "earned_points": i.earned_points, "max_points": i.max_points,
                       "scoring_origin": i.scoring_origin, "confirmed_by_user": i.confirmed_by_user} for i in items],
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
                              owner: str = Depends(require_owner), db: Session = Depends(get_db)):
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
def set_goal(payload: GoalIn, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    next_version = (db.scalar(select(func.max(m.Goal.version)).where(m.Goal.learner_id == owner, m.Goal.subject == payload.subject)) or 0) + 1
    g = m.Goal(learner_id=owner, version=next_version, **payload.model_dump())
    db.add(g); db.commit(); db.refresh(g)
    return {"id": g.id, "version": g.version, "status": "recorded"}

def get_evidence(db: Session, learner_id: str, subject: str):
    """Only first, independent, objective results tied to one knowledge point."""
    rows = db.execute(select(m.AnswerAttempt, m.Exposure, m.QuestionVersion).join(m.Exposure, m.Exposure.id == m.AnswerAttempt.exposure_id).join(m.QuestionVersion, m.QuestionVersion.id == m.AnswerAttempt.question_version_id).join(m.Question, m.Question.id == m.QuestionVersion.question_id).where(m.AnswerAttempt.learner_id == learner_id, m.Question.subject == subject)).all()
    result = []
    for a, ex, q in rows:
        if a.earned_points is None or a.scoring_origin != "reviewed_answer_key" or len(q.knowledge_ids) != 1:
            continue
        result.append(Evidence(source_event_id=a.id, question_version_id=q.id, knowledge_id=q.knowledge_ids[0], earned_points=a.earned_points, max_points=a.max_points, independent=not a.hints_used, is_first_exposure=ex.is_unseen_at_exposure))
    # 已人工确认的校卷逐题得分并入证据（合成键按 item 独立计数）；总分行永不折算（INV-05）。
    school_rows = db.execute(select(m.SchoolExamItem, m.SchoolExam).where(m.SchoolExam.id == m.SchoolExamItem.school_exam_id, m.SchoolExam.learner_id == learner_id, m.SchoolExam.subject == subject, m.SchoolExamItem.confirmed_by_user.is_(True), m.SchoolExamItem.max_points > 0)).all()
    for item, exam in school_rows:
        result.append(Evidence(source_event_id=item.id, question_version_id=f"school-item:{item.id}", knowledge_id=item.knowledge_id, earned_points=item.earned_points, max_points=item.max_points, independent=True, is_first_exposure=True))
    return result

@app.get("/api/guidance/profile")
def profile(subject: Subject, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    return {"subject": subject, "model_version": MODEL_VERSION, "knowledge": summarize(get_evidence(db, owner, subject)), "score_prediction": None, "school_exam_scores_are_not_equated": True}

@app.get("/api/guidance/plan")
def plan(subject: Subject, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    goal = db.execute(select(m.Goal).where(m.Goal.learner_id == owner, m.Goal.subject == subject).order_by(m.Goal.version.desc())).scalars().first()
    if goal is None:
        raise HTTPException(409, detail="GOAL_REQUIRED")
    knowledge = [x[0] for x in db.execute(select(m.QuestionVersion.knowledge_ids).join(m.Question).where(m.Question.subject == subject, m.QuestionVersion.status == "published")).all()]
    # knowledge above is a list of JSON lists; flatten without assuming a fixed taxonomy.
    known_ids = sorted({kid for item in knowledge for kid in item})
    result = make_plan(summarize(get_evidence(db, owner, subject)), goal.target_points, goal.max_points, goal.minutes_per_day, known_ids)
    return {"subject": subject, "goal_version": goal.version, **result}

@app.get("/api/guidance/pool-health")
def pool_health_endpoint(subject: Subject, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    """题池体检：按逻辑题的最新已发布版与 owner 曝光记录如实计数（训练轮换与诊断余量）。
    查询形状刻意与 next_item 一致（最新发布版子查询），不引入第二套选题口径。"""
    latest = select(m.QuestionVersion.question_id, func.max(m.QuestionVersion.version).label("version")).where(m.QuestionVersion.status == "published").group_by(m.QuestionVersion.question_id).subquery()
    versions = db.execute(select(m.QuestionVersion).join(m.Question).join(latest, (m.QuestionVersion.question_id == latest.c.question_id) & (m.QuestionVersion.version == latest.c.version)).where(m.Question.subject == subject, m.QuestionVersion.status == "published")).scalars().all()
    counts = dict(db.execute(select(m.Exposure.question_id, func.count()).where(m.Exposure.learner_id == owner).group_by(m.Exposure.question_id)).all())
    entries = [{"question_id": v.question_id, "knowledge_id": kid, "seen": counts.get(v.question_id, 0) > 0}
               for v in versions for kid in (v.knowledge_ids or [])]
    return {"subject": subject, **pool_health(entries)}

@app.get("/api/guidance/validation")
def validation(subject: Subject, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    """独立未见题复测的可观察对比；不可比或证据不足绝不宣称涨分。"""
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
    return {"subject": subject, **compare_validation(baseline, retest)}
