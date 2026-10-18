"""Private API foundation. Read CODEX_START_HERE.md before extending."""
from __future__ import annotations
import os
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .database import get_db
from . import models as m
from .schemas import SourceIn, QuestionIn, QuestionRevisionOut, AttemptIn, SchoolExamIn, GoalIn, Subject
from .guidance import Evidence, MODEL_VERSION, summarize, make_plan

app = FastAPI(title="书童 ShuTong API", version="0.1.0", docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if x.strip()], allow_credentials=False, allow_methods=["GET","POST"], allow_headers=["Authorization", "Content-Type"])


def require_owner(authorization: str | None = Header(default=None)) -> str:
    import hmac
    expected = os.getenv("SHUTONG_TOKEN")
    if not expected:
        raise HTTPException(503, detail="SHUTONG_TOKEN is not configured")
    if authorization is None or not authorization.startswith("Bearer ") or not hmac.compare_digest(authorization[7:], expected):
        raise HTTPException(401, detail="Owner authorization required", headers={"WWW-Authenticate": "Bearer"})
    return "owner"

@app.get("/health/live")
def live():
    return {"status": "alive"}

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
    q = m.Question(source_document_id=src.id, subject=src.subject)
    db.add(q); db.flush()
    v = m.QuestionVersion(question_id=q.id, version=1, **payload.model_dump(exclude={"source_document_id"}))
    db.add(v); db.commit(); db.refresh(v)
    return {"id": v.id, "question_id": q.id, "status": v.status}

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
    next_version = db.scalar(select(func.max(m.QuestionVersion.version)).where(m.QuestionVersion.question_id == question.id)) + 1
    revised = m.QuestionVersion(question_id=question.id, version=next_version, **payload.model_dump(exclude={"source_document_id"}))
    db.add(revised)
    try:
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
    for v in versions:
        if knowledge_id and knowledge_id not in v.knowledge_ids:
            continue
        seen = db.execute(select(m.Exposure.id).join(m.QuestionVersion, m.Exposure.question_version_id == m.QuestionVersion.id).where(m.Exposure.learner_id == owner, m.QuestionVersion.question_id == v.question_id).limit(1)).first() is not None
        if purpose == "evaluation" and seen:
            continue
        exp = m.Exposure(learner_id=owner, question_version_id=v.id, purpose=purpose, is_unseen_at_exposure=not seen)
        db.add(exp); db.commit(); db.refresh(exp)
        return {"exposure_id": exp.id, "question_version_id": v.id, "purpose": purpose, "unseen_at_exposure": not seen, "stem": v.stem, "kind": v.kind, "options": v.options, "max_points": v.max_points, "subject": subject, "knowledge_ids": v.knowledge_ids}
    raise HTTPException(404, detail="NO_ELIGIBLE_QUESTION")

@app.post("/api/practice/attempts", status_code=201)
def submit_attempt(payload: AttemptIn, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    existing = db.execute(select(m.AnswerAttempt).where(m.AnswerAttempt.learner_id == owner, m.AnswerAttempt.client_attempt_id == payload.client_attempt_id)).scalar_one_or_none()
    if existing:
        if existing.exposure_id != payload.exposure_id or existing.answer != payload.answer or existing.hints_used != payload.hints_used:
            raise HTTPException(409, detail="IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD")
        return {"id": existing.id, "status": "already_recorded", "earned_points": existing.earned_points, "max_points": existing.max_points, "scoring_origin": existing.scoring_origin}
    exp = db.get(m.Exposure, payload.exposure_id)
    if exp is None or exp.learner_id != owner:
        raise HTTPException(404, detail="exposure not found")
    v = db.get(m.QuestionVersion, exp.question_version_id)
    previous = db.execute(select(m.AnswerAttempt.id).where(m.AnswerAttempt.exposure_id == exp.id).limit(1)).first()
    if previous:
        raise HTTPException(409, detail="EXPOSURE_ALREADY_SUBMITTED")
    # Simple objective grading only; subjective scoring remains unverified.
    if v.kind == "single_choice":
        earned = v.max_points if payload.answer.strip() == v.correct_answer.strip() else 0.0
        origin = "reviewed_answer_key"
    else:
        earned = None
        origin = "ungraded_subjective"
    attempt = m.AnswerAttempt(learner_id=owner, client_attempt_id=payload.client_attempt_id, exposure_id=exp.id, question_version_id=v.id, answer=payload.answer, earned_points=earned, max_points=v.max_points, scoring_origin=origin, hints_used=payload.hints_used)
    db.add(attempt); db.commit(); db.refresh(attempt)
    return {"id": attempt.id, "status": "recorded", "earned_points": earned, "max_points": v.max_points, "scoring_origin": origin, "evaluation_valid_unseen": exp.purpose == "evaluation" and exp.is_unseen_at_exposure and not payload.hints_used}

@app.post("/api/school-exams", status_code=201)
def add_school_exam(payload: SchoolExamIn, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    record = m.SchoolExam(learner_id=owner, **payload.model_dump())
    db.add(record); db.commit(); db.refresh(record)
    return {"id": record.id, "status": "user_confirmed" if record.confirmed_by_user else "unconfirmed", "knowledge_evidence_created": False}

@app.get("/api/school-exams")
def get_school_exams(subject: Subject, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    exams = db.execute(select(m.SchoolExam).where(m.SchoolExam.learner_id == owner, m.SchoolExam.subject == subject).order_by(m.SchoolExam.exam_date.desc())).scalars().all()
    return [{"id": e.id, "title": e.title, "exam_date": str(e.exam_date), "earned_points": e.earned_points, "max_points": e.max_points, "confirmed_by_user": e.confirmed_by_user} for e in exams]

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
