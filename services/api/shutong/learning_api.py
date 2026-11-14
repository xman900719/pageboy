"""学生端智能综合练习、错题 AI 苏格拉底引导、成长状态与知识图谱 API 路由。"""

from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import ai_tutor
from . import models as m
from .auth import require_student
from .database import get_db
from .guidance import (
    Evidence,
    MODEL_VERSION,
    compose_practice_plan,
    compute_knowledge_mastery,
    summarize_growth,
)
from .schemas import (
    GrowthStatusOut,
    KnowledgeGraphOut,
    PracticeQuestionPayloadOut,
    PracticeSessionCompleteOut,
    PracticeSessionCreateIn,
    PracticeSessionItemPlanOut,
    PracticeSessionOut,
    Subject,
    TutorMessageIn,
    TutorSessionOut,
    TutorTurnOut,
    WrongQuestionSummaryOut,
)
from .taxonomy_bridge import (
    get_elective_codes,
    get_prerequisite_edges,
    load_candidate_contracts,
    resolve_question_to_candidate_codes,
)
from .topic_labels import get_topic_label

router = APIRouter(tags=["learning"])


def get_evidence(db: Session, learner_id: str, subject: str) -> list[Evidence]:
    """收集指定学科有效客观作答证据（单知识点已审核真题 + 已人工确认的校考逐题明细）。"""
    rows = db.execute(
        select(m.AnswerAttempt, m.Exposure, m.QuestionVersion)
        .join(m.Exposure, m.Exposure.id == m.AnswerAttempt.exposure_id)
        .join(m.QuestionVersion, m.QuestionVersion.id == m.AnswerAttempt.question_version_id)
        .join(m.Question, m.Question.id == m.QuestionVersion.question_id)
        .where(m.AnswerAttempt.learner_id == learner_id, m.Question.subject == subject)
    ).all()
    result: list[Evidence] = []
    for a, ex, q in rows:
        if a.earned_points is None or a.scoring_origin != "reviewed_answer_key" or len(q.knowledge_ids) != 1:
            continue
        result.append(
            Evidence(
                source_event_id=a.id,
                question_version_id=q.id,
                knowledge_id=q.knowledge_ids[0],
                earned_points=a.earned_points,
                max_points=a.max_points,
                independent=not a.hints_used,
                is_first_exposure=ex.is_unseen_at_exposure,
            )
        )
    # 已人工确认的校卷逐题得分并入证据（合成键按 item 独立计数）；总分行永不折算（INV-05）。
    school_rows = db.execute(
        select(m.SchoolExamItem, m.SchoolExam).where(
            m.SchoolExam.id == m.SchoolExamItem.school_exam_id,
            m.SchoolExam.learner_id == learner_id,
            m.SchoolExam.subject == subject,
            m.SchoolExamItem.confirmed_by_user.is_(True),
            m.SchoolExamItem.max_points > 0,
        )
    ).all()
    for item, _exam in school_rows:
        result.append(
            Evidence(
                source_event_id=item.id,
                question_version_id=f"school-item:{item.id}",
                knowledge_id=item.knowledge_id,
                earned_points=item.earned_points,
                max_points=item.max_points,
                independent=True,
                is_first_exposure=True,
            )
        )
    return result


def _load_effective_knowledge_nodes(db: Session, subject: str) -> tuple[list[dict], str | None]:
    """加载有效非选学知识节点（优先读取最新发布版本快照，未发布时优雅回退到未驳回节点/契约）。"""
    contract_by_code = {c["code"]: c for c in load_candidate_contracts(subject)}
    elective_codes = get_elective_codes(subject)

    latest_release = db.execute(
        select(m.KnowledgeTaxonomyRelease)
        .where(m.KnowledgeTaxonomyRelease.subject == subject)
        .order_by(m.KnowledgeTaxonomyRelease.published_at.desc(), m.KnowledgeTaxonomyRelease.id.desc())
        .limit(1)
    ).scalar_one_or_none()

    if latest_release is not None and isinstance(latest_release.snapshot, dict):
        raw_nodes = latest_release.snapshot.get("nodes") or []
        nodes: list[dict] = []
        for n in raw_nodes:
            code = n.get("code")
            if not code or n.get("is_elective") or code in elective_codes:
                continue
            meta = contract_by_code.get(code, {})
            nodes.append(
                {
                    "code": code,
                    "name": n.get("name") or meta.get("name") or code,
                    "domain": n.get("domain") or meta.get("domain"),
                    "parent_code": n.get("parent_code") if "parent_code" in n else meta.get("parent_code"),
                    "level": n.get("level") or meta.get("level") or 2,
                    "description": n.get("description") or meta.get("description"),
                    "is_elective": False,
                }
            )
        if nodes:
            return nodes, latest_release.release_version

    db_nodes = db.execute(
        select(m.KnowledgeNode)
        .where(
            m.KnowledgeNode.subject == subject,
            m.KnowledgeNode.status == "active",
            m.KnowledgeNode.is_elective.is_(False),
        )
        .order_by(m.KnowledgeNode.created_at.asc(), m.KnowledgeNode.code.asc())
    ).scalars().all()
    if db_nodes:
        id_to_code = {n.id: n.code for n in db_nodes}
        latest_ver_sub = (
            select(
                m.KnowledgeNodeVersion.node_id,
                func.max(m.KnowledgeNodeVersion.version).label("max_ver"),
            )
            .where(m.KnowledgeNodeVersion.node_id.in_([n.id for n in db_nodes]))
            .group_by(m.KnowledgeNodeVersion.node_id)
            .subquery()
        )
        ver_rows = db.execute(
            select(m.KnowledgeNodeVersion).join(
                latest_ver_sub,
                (m.KnowledgeNodeVersion.node_id == latest_ver_sub.c.node_id)
                & (m.KnowledgeNodeVersion.version == latest_ver_sub.c.max_ver),
            )
        ).scalars().all()
        ver_by_node = {v.node_id: v for v in ver_rows}
        nodes = []
        for n in db_nodes:
            if n.code in elective_codes:
                continue
            ver = ver_by_node.get(n.id)
            if ver is not None and ver.review_status == "rejected":
                continue
            meta = contract_by_code.get(n.code, {})
            parent_code = (
                (ver.parent_code if ver is not None and ver.parent_code else None)
                or (id_to_code.get(n.parent_id) if n.parent_id else None)
                or meta.get("parent_code")
            )
            nodes.append(
                {
                    "code": n.code,
                    "name": (ver.name if ver is not None else None) or meta.get("name") or n.code,
                    "domain": meta.get("domain"),
                    "parent_code": parent_code,
                    "level": meta.get("level", 2),
                    "description": (ver.description if ver is not None else None) or meta.get("description"),
                    "is_elective": False,
                }
            )
        if nodes:
            return nodes, None

    fallback = [
        {
            "code": c["code"],
            "name": c["name"],
            "domain": c.get("domain"),
            "parent_code": c.get("parent_code"),
            "level": c.get("level", 2),
            "description": c.get("description"),
            "is_elective": False,
        }
        for c in contract_by_code.values()
        if not c.get("is_elective")
    ]
    return fallback, None


def _get_mapped_evidence(db: Session, learner_id: str, subject: str, valid_codes: set[str]) -> list[Evidence]:
    """将作答证据中的旧/新考点编码统一映射到当前有效非选学节点。"""
    raw_evidence = get_evidence(db, learner_id, subject)
    mapped: list[Evidence] = []
    for ev in raw_evidence:
        targets = resolve_question_to_candidate_codes(subject, [ev.knowledge_id])
        if not targets and ev.knowledge_id in valid_codes:
            targets = [ev.knowledge_id]
        for code in targets:
            if code in valid_codes:
                mapped.append(
                    Evidence(
                        source_event_id=ev.source_event_id,
                        question_version_id=ev.question_version_id,
                        knowledge_id=code,
                        earned_points=ev.earned_points,
                        max_points=ev.max_points,
                        independent=ev.independent,
                        is_first_exposure=ev.is_first_exposure,
                    )
                )
    return mapped


def _resolve_question_knowledge(
    subject: str, raw_codes: list[str] | None, name_map: dict[str, str]
) -> tuple[list[str], list[str]]:
    """解析题目对应的当前知识点编码与面向学生的自然语言标题。"""
    cand_codes = resolve_question_to_candidate_codes(subject, raw_codes)
    if cand_codes:
        titles = [name_map.get(code) or get_topic_label(code) for code in cand_codes]
        return cand_codes, titles
    fallback_codes = list(raw_codes or [])
    titles = [name_map.get(code) or get_topic_label(code) for code in fallback_codes]
    return fallback_codes, titles


def _serialize_question_payload(
    exp: m.Exposure,
    v: m.QuestionVersion,
    subject: str,
    selection_reason: str | None,
    name_map: dict[str, str],
) -> PracticeQuestionPayloadOut:
    """组装面向学生的作答题目载荷，绝不附带参考答案。"""
    _codes, titles = _resolve_question_knowledge(subject, v.knowledge_ids, name_map)
    return PracticeQuestionPayloadOut(
        exposure_id=exp.id,
        question_version_id=v.id,
        purpose=exp.purpose,
        unseen_at_exposure=exp.is_unseen_at_exposure,
        stem=v.stem,
        kind=v.kind,
        group_context=v.group_context,
        media_attachment_id=v.media_attachment_id,
        options=list(v.options or []),
        max_points=v.max_points,
        subject=subject,
        selection_reason=selection_reason,
        knowledge_titles=titles,
    )


def _create_exposure_for_item(
    db: Session,
    owner: str,
    purpose: str,
    item: m.PracticeSessionItem,
    version: m.QuestionVersion,
) -> m.Exposure | None:
    """为练习槽位落库曝光记录，严格遵循首次未见与并发部分唯一约束。"""
    seen_now = (
        db.scalar(
            select(func.count())
            .select_from(m.Exposure)
            .where(m.Exposure.learner_id == owner, m.Exposure.question_id == version.question_id)
        )
        > 0
    )
    if purpose == "evaluation" and seen_now:
        return None
    exp = m.Exposure(
        learner_id=owner,
        question_id=version.question_id,
        question_version_id=version.id,
        purpose=purpose,
        is_unseen_at_exposure=not seen_now,
    )
    db.add(exp)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        if purpose == "evaluation":
            return None
        recheck_seen = (
            db.scalar(
                select(func.count())
                .select_from(m.Exposure)
                .where(m.Exposure.learner_id == owner, m.Exposure.question_id == version.question_id)
            )
            > 0
        )
        exp = m.Exposure(
            learner_id=owner,
            question_id=version.question_id,
            question_version_id=version.id,
            purpose=purpose,
            is_unseen_at_exposure=not recheck_seen,
        )
        db.add(exp)
        db.flush()

    item.exposure_id = exp.id
    db.commit()
    db.refresh(exp)
    return exp


def _build_session_state(
    db: Session,
    owner: str,
    session_obj: m.PracticeSession,
    name_map: dict[str, str],
) -> PracticeSessionOut:
    """读取练习会话的实时槽位进度与当前待作答题目（刷新不重复消耗曝光）。"""
    items = db.execute(
        select(m.PracticeSessionItem)
        .where(m.PracticeSessionItem.session_id == session_obj.id)
        .order_by(m.PracticeSessionItem.seq.asc())
    ).scalars().all()

    exposure_ids = [it.exposure_id for it in items if it.exposure_id]
    attempts_by_exp: dict[str, m.AnswerAttempt] = {}
    exposures_by_id: dict[str, m.Exposure] = {}
    if exposure_ids:
        for att in db.execute(
            select(m.AnswerAttempt).where(m.AnswerAttempt.exposure_id.in_(exposure_ids))
        ).scalars().all():
            attempts_by_exp[att.exposure_id] = att
        for exp in db.execute(
            select(m.Exposure).where(m.Exposure.id.in_(exposure_ids))
        ).scalars().all():
            exposures_by_id[exp.id] = exp

    version_ids = [it.question_version_id for it in items]
    versions_by_id: dict[str, m.QuestionVersion] = {}
    if version_ids:
        for v in db.execute(
            select(m.QuestionVersion).where(m.QuestionVersion.id.in_(version_ids))
        ).scalars().all():
            versions_by_id[v.id] = v

    plan_items: list[PracticeSessionItemPlanOut] = []
    completed_count = 0
    current_item_payload: PracticeQuestionPayloadOut | None = None

    for it in items:
        att = attempts_by_exp.get(it.exposure_id) if it.exposure_id else None
        v = versions_by_id.get(it.question_version_id)
        answered = att is not None
        if answered:
            completed_count += 1
        elif it.exposure_id and current_item_payload is None and v is not None:
            exp = exposures_by_id.get(it.exposure_id)
            if exp is not None:
                current_item_payload = _serialize_question_payload(
                    exp, v, session_obj.subject, it.selection_reason, name_map
                )
        plan_items.append(
            PracticeSessionItemPlanOut(
                seq=it.seq,
                question_version_id=it.question_version_id,
                selection_reason=it.selection_reason,
                focus_knowledge_codes=list(it.target_knowledge_codes or []),
                answered=answered,
                attempt_id=att.id if att is not None else None,
                earned_points=att.earned_points if att is not None else None,
                max_points=v.max_points if v is not None else 0.0,
            )
        )

    raw_summary = dict(session_obj.composition_summary or {})
    focus_code = raw_summary.get("focus_knowledge_code")
    clean_summary = {k: int(val) for k, val in raw_summary.items() if isinstance(val, (int, float))}

    return PracticeSessionOut(
        id=session_obj.id,
        subject=session_obj.subject,
        purpose=session_obj.purpose,
        status=session_obj.status,
        target_count=session_obj.target_count,
        total_items=len(items),
        completed_count=completed_count,
        focus_knowledge_code=focus_code if isinstance(focus_code, str) else None,
        composition_summary=clean_summary,
        items=plan_items,
        current_item=current_item_payload,
    )


def _advance_session_to_next(
    db: Session,
    owner: str,
    session_obj: m.PracticeSession,
    name_map: dict[str, str],
) -> PracticeSessionOut:
    """推进会话到下一道未作答槽位；若当前已有未作答曝光则直接恢复，避免空烧未见题。"""
    state = _build_session_state(db, owner, session_obj, name_map)
    if state.current_item is not None or session_obj.status == "completed":
        return state

    items = db.execute(
        select(m.PracticeSessionItem)
        .where(
            m.PracticeSessionItem.session_id == session_obj.id,
            m.PracticeSessionItem.exposure_id.is_(None),
        )
        .order_by(m.PracticeSessionItem.seq.asc())
    ).scalars().all()

    for it in items:
        v = db.get(m.QuestionVersion, it.question_version_id)
        if v is None or v.status != "published":
            continue
        exp = _create_exposure_for_item(db, owner, session_obj.purpose, it, v)
        if exp is not None:
            break

    return _build_session_state(db, owner, session_obj, name_map)


@router.post("/api/practice/sessions", status_code=201, response_model=PracticeSessionOut)
def create_practice_session(
    payload: PracticeSessionCreateIn,
    student: str = Depends(require_student),
    db: Session = Depends(get_db),
):
    """结合知识点体系、题库曝光历史与学生能力缺失综合编制一轮智能练习，并露出第 1 题。"""
    owner = student
    nodes, _release_ver = _load_effective_knowledge_nodes(db, payload.subject)
    valid_codes = {n["code"] for n in nodes}
    name_map = {n["code"]: n["name"] for n in nodes}

    if payload.focus_knowledge_code and payload.focus_knowledge_code not in valid_codes:
        raise HTTPException(status_code=404, detail="KNOWLEDGE_NODE_NOT_FOUND")

    evidence = _get_mapped_evidence(db, owner, payload.subject, valid_codes)
    mastery_items = compute_knowledge_mastery(nodes, evidence)
    edges = get_prerequisite_edges(payload.subject, valid_codes=valid_codes)

    latest = (
        select(
            m.QuestionVersion.question_id,
            func.max(m.QuestionVersion.version).label("version"),
        )
        .where(m.QuestionVersion.status == "published")
        .group_by(m.QuestionVersion.question_id)
        .subquery()
    )
    versions = db.execute(
        select(m.QuestionVersion)
        .join(m.Question)
        .join(
            latest,
            (m.QuestionVersion.question_id == latest.c.question_id)
            & (m.QuestionVersion.version == latest.c.version),
        )
        .where(m.Question.subject == payload.subject, m.QuestionVersion.status == "published")
        .order_by(m.QuestionVersion.created_at, m.QuestionVersion.id)
    ).scalars().all()

    exposure_counts = dict(
        db.execute(
            select(m.Exposure.question_id, func.count())
            .where(m.Exposure.learner_id == owner)
            .group_by(m.Exposure.question_id)
        ).all()
    )

    candidates = []
    for v in versions:
        cand_codes, _ = _resolve_question_knowledge(payload.subject, v.knowledge_ids, name_map)
        candidates.append(
            {
                "question_id": v.question_id,
                "question_version_id": v.id,
                "knowledge_codes": cand_codes,
                "seen_count": exposure_counts.get(v.question_id, 0),
                "created_sort_key": v.created_at.isoformat() if v.created_at else "",
            }
        )

    plan = compose_practice_plan(
        candidates=candidates,
        mastery_items=mastery_items,
        prerequisite_edges=edges,
        target_count=payload.target_count,
        purpose=payload.purpose,
        focus_knowledge_code=payload.focus_knowledge_code,
    )
    if not plan["items"]:
        raise HTTPException(status_code=404, detail="NO_ELIGIBLE_QUESTION")

    comp_payload = dict(plan["composition_summary"])
    if payload.focus_knowledge_code:
        comp_payload["focus_knowledge_code"] = payload.focus_knowledge_code

    session_obj = m.PracticeSession(
        learner_id=owner,
        subject=payload.subject,
        purpose=payload.purpose,
        target_count=payload.target_count,
        status="active",
        composition_summary=comp_payload,
    )
    db.add(session_obj)
    db.flush()

    for planned in plan["items"]:
        db.add(
            m.PracticeSessionItem(
                session_id=session_obj.id,
                seq=planned["seq"],
                question_id=planned["question_id"],
                question_version_id=planned["question_version_id"],
                selection_reason=planned["selection_reason"],
                target_knowledge_codes=planned["target_knowledge_codes"],
            )
        )
    db.commit()
    db.refresh(session_obj)
    return _advance_session_to_next(db, owner, session_obj, name_map)


@router.get("/api/practice/sessions/{session_id}", response_model=PracticeSessionOut)
def get_practice_session(
    session_id: str,
    student: str = Depends(require_student),
    db: Session = Depends(get_db),
):
    """查询练习会话当前进度与待作答题面（只读，不新增曝光）。"""
    session_obj = db.get(m.PracticeSession, session_id)
    if session_obj is None or session_obj.learner_id != student:
        raise HTTPException(status_code=404, detail="practice session not found")
    nodes, _ = _load_effective_knowledge_nodes(db, session_obj.subject)
    name_map = {n["code"]: n["name"] for n in nodes}
    return _build_session_state(db, student, session_obj, name_map)


@router.post("/api/practice/sessions/{session_id}/next", response_model=PracticeSessionOut)
def next_session_item(
    session_id: str,
    student: str = Depends(require_student),
    db: Session = Depends(get_db),
):
    """获取当前练习会话的下一道待作答题目（已有未作答曝光时直接续答）。"""
    session_obj = db.get(m.PracticeSession, session_id)
    if session_obj is None or session_obj.learner_id != student:
        raise HTTPException(status_code=404, detail="practice session not found")
    nodes, _ = _load_effective_knowledge_nodes(db, session_obj.subject)
    name_map = {n["code"]: n["name"] for n in nodes}
    return _advance_session_to_next(db, student, session_obj, name_map)


@router.post("/api/practice/sessions/{session_id}/complete", response_model=PracticeSessionCompleteOut)
def complete_practice_session(
    session_id: str,
    student: str = Depends(require_student),
    db: Session = Depends(get_db),
):
    """结束本轮练习并结算错题清单（不直接返回正确答案，由 AI 引导讲评）。"""
    session_obj = db.get(m.PracticeSession, session_id)
    if session_obj is None or session_obj.learner_id != student:
        raise HTTPException(status_code=404, detail="practice session not found")

    if session_obj.status != "completed":
        session_obj.status = "completed"
        session_obj.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(session_obj)

    nodes, _ = _load_effective_knowledge_nodes(db, session_obj.subject)
    name_map = {n["code"]: n["name"] for n in nodes}

    items = db.execute(
        select(m.PracticeSessionItem)
        .where(m.PracticeSessionItem.session_id == session_obj.id)
        .order_by(m.PracticeSessionItem.seq.asc())
    ).scalars().all()

    exposure_ids = [it.exposure_id for it in items if it.exposure_id]
    attempts_by_exp: dict[str, m.AnswerAttempt] = {}
    if exposure_ids:
        for att in db.execute(
            select(m.AnswerAttempt).where(m.AnswerAttempt.exposure_id.in_(exposure_ids))
        ).scalars().all():
            attempts_by_exp[att.exposure_id] = att

    attempt_ids = [att.id for att in attempts_by_exp.values()]
    tutor_by_attempt: dict[str, str] = {}
    if attempt_ids:
        for ts in db.execute(
            select(m.AiTutorSession).where(m.AiTutorSession.attempt_id.in_(attempt_ids))
        ).scalars().all():
            tutor_by_attempt[ts.attempt_id] = ts.id

    answered_count = 0
    correct_count = 0
    wrong_count = 0
    subjective_count = 0
    wrong_items: list[WrongQuestionSummaryOut] = []

    for it in items:
        if not it.exposure_id:
            continue
        att = attempts_by_exp.get(it.exposure_id)
        if att is None:
            continue
        answered_count += 1
        v = db.get(m.QuestionVersion, att.question_version_id)
        if v is None:
            continue
        if att.earned_points is None:
            subjective_count += 1
            continue
        if att.earned_points >= att.max_points:
            correct_count += 1
            continue

        wrong_count += 1
        codes, titles = _resolve_question_knowledge(session_obj.subject, v.knowledge_ids, name_map)
        wrong_items.append(
            WrongQuestionSummaryOut(
                attempt_id=att.id,
                question_version_id=v.id,
                subject=session_obj.subject,
                stem=v.stem,
                kind=v.kind,
                options=list(v.options or []),
                student_answer=att.answer,
                earned_points=att.earned_points,
                max_points=att.max_points,
                selection_reason=it.selection_reason,
                knowledge_codes=codes,
                knowledge_titles=titles,
                tutor_session_id=tutor_by_attempt.get(att.id),
                created_at=att.created_at,
            )
        )

    return PracticeSessionCompleteOut(
        session_id=session_obj.id,
        status="completed",
        answered_count=answered_count,
        correct_count=correct_count,
        wrong_count=wrong_count,
        subjective_count=subjective_count,
        wrong_items=wrong_items,
    )


@router.get("/api/practice/wrong-attempts", response_model=list[WrongQuestionSummaryOut])
def list_wrong_attempts(
    subject: Subject,
    limit: int = Query(default=20, ge=1, le=50),
    student: str = Depends(require_student),
    db: Session = Depends(get_db),
):
    """列出学生指定学科近期错题记录，支持随时打开 AI 苏格拉底引导复习。"""
    nodes, _ = _load_effective_knowledge_nodes(db, subject)
    name_map = {n["code"]: n["name"] for n in nodes}

    rows = db.execute(
        select(m.AnswerAttempt, m.QuestionVersion)
        .join(m.QuestionVersion, m.QuestionVersion.id == m.AnswerAttempt.question_version_id)
        .join(m.Question, m.Question.id == m.QuestionVersion.question_id)
        .where(
            m.AnswerAttempt.learner_id == student,
            m.Question.subject == subject,
            m.AnswerAttempt.earned_points.is_not(None),
            m.AnswerAttempt.earned_points < m.AnswerAttempt.max_points,
        )
        .order_by(m.AnswerAttempt.created_at.desc(), m.AnswerAttempt.id.desc())
        .limit(limit)
    ).all()

    attempt_ids = [a.id for a, _ in rows]
    tutor_by_attempt: dict[str, str] = {}
    if attempt_ids:
        for ts in db.execute(
            select(m.AiTutorSession).where(m.AiTutorSession.attempt_id.in_(attempt_ids))
        ).scalars().all():
            tutor_by_attempt[ts.attempt_id] = ts.id

    out: list[WrongQuestionSummaryOut] = []
    for att, v in rows:
        codes, titles = _resolve_question_knowledge(subject, v.knowledge_ids, name_map)
        out.append(
            WrongQuestionSummaryOut(
                attempt_id=att.id,
                question_version_id=v.id,
                subject=subject,
                stem=v.stem,
                kind=v.kind,
                options=list(v.options or []),
                student_answer=att.answer,
                earned_points=att.earned_points,
                max_points=att.max_points,
                selection_reason=None,
                knowledge_codes=codes,
                knowledge_titles=titles,
                tutor_session_id=tutor_by_attempt.get(att.id),
                created_at=att.created_at,
            )
        )
    return out


def _encode_turn_model(model_name: str | None, sanitized: bool) -> str | None:
    if not model_name:
        return "[guarded]" if sanitized else None
    return f"{model_name}[guarded]" if sanitized else model_name


def _decode_turn_model(model_used: str | None) -> tuple[str | None, bool]:
    if not model_used:
        return None, False
    if model_used.endswith("[guarded]"):
        raw = model_used[: -len("[guarded]")].strip()
        return (raw or None), True
    return model_used, False


def _serialize_tutor_session(
    db: Session,
    session_obj: m.AiTutorSession,
    stem: str,
    student_answer: str,
    knowledge_titles: list[str],
) -> TutorSessionOut:
    """序列化 AI 错题引导会话与完整对话轮次。"""
    turns = db.execute(
        select(m.AiTutorTurn)
        .where(m.AiTutorTurn.tutor_session_id == session_obj.id)
        .order_by(m.AiTutorTurn.turn_index.asc())
    ).scalars().all()
    latest_model: str | None = None
    out_turns: list[TutorTurnOut] = []
    for t in turns:
        clean_model, guarded = _decode_turn_model(t.model_used)
        if clean_model:
            latest_model = clean_model
        out_turns.append(
            TutorTurnOut(
                id=t.id,
                turn_index=t.turn_index,
                role=t.role,
                content=t.content,
                sanitized_guard_triggered=guarded,
                created_at=t.created_at,
            )
        )
    return TutorSessionOut(
        started=True,
        id=session_obj.id,
        attempt_id=session_obj.attempt_id,
        status=session_obj.status,
        model_name=latest_model,
        stem=stem,
        student_answer=student_answer,
        knowledge_titles=knowledge_titles,
        turns=out_turns,
    )


def _load_attempt_context(
    db: Session, student: str, attempt_id: str
) -> tuple[m.AnswerAttempt, m.QuestionVersion, m.Question, list[str]]:
    """校验作答归属并加载题目上下文与学生可读知识点名称。"""
    att = db.get(m.AnswerAttempt, attempt_id)
    if att is None or att.learner_id != student:
        raise HTTPException(status_code=404, detail="attempt not found")
    v = db.get(m.QuestionVersion, att.question_version_id)
    q = db.get(m.Question, v.question_id) if v is not None else None
    if v is None or q is None:
        raise HTTPException(status_code=404, detail="question version not found")
    nodes, _ = _load_effective_knowledge_nodes(db, q.subject)
    name_map = {n["code"]: n["name"] for n in nodes}
    _codes, titles = _resolve_question_knowledge(q.subject, v.knowledge_ids, name_map)
    return att, v, q, titles


@router.get("/api/tutor/attempts/{attempt_id}", response_model=TutorSessionOut)
def get_tutor_for_attempt(
    attempt_id: str,
    student: str = Depends(require_student),
    db: Session = Depends(get_db),
):
    """读取指定作答记录关联的 AI 错题引导对话（尚未发起时返回 started=false）。"""
    att, v, _q, titles = _load_attempt_context(db, student, attempt_id)
    existing = db.execute(
        select(m.AiTutorSession).where(
            m.AiTutorSession.attempt_id == att.id,
            m.AiTutorSession.learner_id == student,
        )
    ).scalar_one_or_none()
    if existing is None:
        return TutorSessionOut(
            started=False,
            attempt_id=att.id,
            stem=v.stem,
            student_answer=att.answer,
            knowledge_titles=titles,
            turns=[],
        )
    return _serialize_tutor_session(db, existing, v.stem, att.answer, titles)


@router.post("/api/tutor/attempts/{attempt_id}/start", status_code=201, response_model=TutorSessionOut)
def start_tutor_for_attempt(
    attempt_id: str,
    student: str = Depends(require_student),
    db: Session = Depends(get_db),
):
    """启动 AI 苏格拉底式错题引导（幂等：已启动直接返回历史对话，绝不直接泄露答案）。"""
    att, v, q, titles = _load_attempt_context(db, student, attempt_id)
    existing = db.execute(
        select(m.AiTutorSession).where(
            m.AiTutorSession.attempt_id == att.id,
            m.AiTutorSession.learner_id == student,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return _serialize_tutor_session(db, existing, v.stem, att.answer, titles)

    system_prompt = ai_tutor.build_socratic_system_prompt(
        subject=q.subject,
        stem=v.stem,
        choices=list(v.options or []),
        student_answer=att.answer,
        correct_answer=v.correct_answer,
        knowledge_titles=titles,
    )
    try:
        reply, sanitized, model_name = ai_tutor.request_socratic_reply(
            system_prompt=system_prompt,
            history_turns=[
                {
                    "role": "user",
                    "content": "我做错了这道题，请先肯定我可能的思考切入点，再提出1个简短的引导性问题帮我自主找出错因。注意绝对不要直接告诉我答案。",
                }
            ],
            correct_answer=v.correct_answer,
            student_answer=att.answer,
            choices=list(v.options or []),
            knowledge_titles=titles,
            hint_level=1,
        )
    except (ai_tutor.AiTutorConfigError, ai_tutor.AiTutorUnavailableError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    tutor_session = m.AiTutorSession(
        learner_id=student,
        attempt_id=att.id,
        question_version_id=v.id,
        status="active",
    )
    db.add(tutor_session)
    db.flush()
    db.add(
        m.AiTutorTurn(
            tutor_session_id=tutor_session.id,
            turn_index=1,
            role="assistant",
            content=reply,
            model_used=_encode_turn_model(model_name, sanitized),
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        winner = db.execute(
            select(m.AiTutorSession).where(
                m.AiTutorSession.attempt_id == att.id,
                m.AiTutorSession.learner_id == student,
            )
        ).scalar_one_or_none()
        if winner is not None:
            return _serialize_tutor_session(db, winner, v.stem, att.answer, titles)
        raise
    db.refresh(tutor_session)
    return _serialize_tutor_session(db, tutor_session, v.stem, att.answer, titles)


@router.post("/api/tutor/sessions/{tutor_session_id}/message", response_model=TutorSessionOut)
def send_tutor_message(
    tutor_session_id: str,
    payload: TutorMessageIn,
    student: str = Depends(require_student),
    db: Session = Depends(get_db),
):
    """发送学生思考回复并获取 AI 下一轮苏格拉底引导提示。"""
    tutor_session = db.get(m.AiTutorSession, tutor_session_id)
    if tutor_session is None or tutor_session.learner_id != student:
        raise HTTPException(status_code=404, detail="tutor session not found")

    att, v, q, titles = _load_attempt_context(db, student, tutor_session.attempt_id)
    existing_turns = db.execute(
        select(m.AiTutorTurn)
        .where(m.AiTutorTurn.tutor_session_id == tutor_session.id)
        .order_by(m.AiTutorTurn.turn_index.asc())
    ).scalars().all()

    history_turns = [{"role": t.role, "content": t.content} for t in existing_turns]
    user_text = payload.content.strip()
    history_turns.append({"role": "user", "content": user_text})
    assistant_count = sum(1 for t in existing_turns if t.role == "assistant")

    system_prompt = ai_tutor.build_socratic_system_prompt(
        subject=q.subject,
        stem=v.stem,
        choices=list(v.options or []),
        student_answer=att.answer,
        correct_answer=v.correct_answer,
        knowledge_titles=titles,
    )
    try:
        reply, sanitized, model_name = ai_tutor.request_socratic_reply(
            system_prompt=system_prompt,
            history_turns=history_turns,
            correct_answer=v.correct_answer,
            student_answer=att.answer,
            choices=list(v.options or []),
            knowledge_titles=titles,
            hint_level=assistant_count + 1,
        )
    except (ai_tutor.AiTutorConfigError, ai_tutor.AiTutorUnavailableError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    next_idx = (existing_turns[-1].turn_index if existing_turns else 0) + 1
    db.add(
        m.AiTutorTurn(
            tutor_session_id=tutor_session.id,
            turn_index=next_idx,
            role="user",
            content=user_text,
            model_used=None,
        )
    )
    db.add(
        m.AiTutorTurn(
            tutor_session_id=tutor_session.id,
            turn_index=next_idx + 1,
            role="assistant",
            content=reply,
            model_used=_encode_turn_model(model_name, sanitized),
        )
    )
    tutor_session.updated_at = datetime.now(timezone.utc)
    db.commit()
    return _serialize_tutor_session(db, tutor_session, v.stem, att.answer, titles)


@router.get("/api/growth/status", response_model=GrowthStatusOut)
def growth_status(
    subject: Subject,
    student: str = Depends(require_student),
    db: Session = Depends(get_db),
):
    """返回学生成长状态：优势知识点、薄弱不足、领域雷达、近期错题数与当前学习目标。"""
    nodes, release_version = _load_effective_knowledge_nodes(db, subject)
    valid_codes = {n["code"] for n in nodes}
    evidence = _get_mapped_evidence(db, student, subject, valid_codes)
    mastery_items = compute_knowledge_mastery(nodes, evidence)
    growth = summarize_growth(mastery_items)

    recent_wrong_count = (
        db.scalar(
            select(func.count())
            .select_from(m.AnswerAttempt)
            .join(m.QuestionVersion, m.QuestionVersion.id == m.AnswerAttempt.question_version_id)
            .join(m.Question, m.Question.id == m.QuestionVersion.question_id)
            .where(
                m.AnswerAttempt.learner_id == student,
                m.Question.subject == subject,
                m.AnswerAttempt.earned_points.is_not(None),
                m.AnswerAttempt.earned_points < m.AnswerAttempt.max_points,
            )
        )
        or 0
    )

    latest_goal = db.execute(
        select(m.Goal)
        .where(m.Goal.learner_id == student, m.Goal.subject == subject)
        .order_by(m.Goal.version.desc())
        .limit(1)
    ).scalar_one_or_none()
    current_goal = (
        {
            "version": latest_goal.version,
            "target_points": latest_goal.target_points,
            "max_points": latest_goal.max_points,
            "minutes_per_day": latest_goal.minutes_per_day,
        }
        if latest_goal is not None
        else None
    )

    return GrowthStatusOut(
        subject=subject,
        model_version=MODEL_VERSION,
        release_version=release_version,
        planning_threshold=growth["planning_threshold"],
        summary_counts=growth["summary_counts"],
        strengths=growth["strengths"],
        weaknesses=growth["weaknesses"],
        developing=growth["developing"],
        untested_highlights=growth["untested_highlights"],
        domain_radar=growth["domain_radar"],
        recent_wrong_count=recent_wrong_count,
        current_goal=current_goal,
        disclaimer=growth["disclaimer"],
    )


@router.get("/api/knowledge/graph", response_model=KnowledgeGraphOut)
def knowledge_graph(
    subject: Subject,
    student: str = Depends(require_student),
    db: Session = Depends(get_db),
):
    """返回学生端知识图谱（已发布非选学节点 + 层级/前置边 + 学生实时掌握状态高亮）。"""
    nodes, release_version = _load_effective_knowledge_nodes(db, subject)
    valid_codes = {n["code"] for n in nodes}
    evidence = _get_mapped_evidence(db, student, subject, valid_codes)
    mastery_items = compute_knowledge_mastery(nodes, evidence)
    growth = summarize_growth(mastery_items)

    edges: list[dict] = []
    for n in nodes:
        if n.get("parent_code") and n["parent_code"] in valid_codes:
            edges.append(
                {
                    "source": n["parent_code"],
                    "target": n["code"],
                    "relation": "所属模块",
                    "edge_type": "hierarchy",
                }
            )
    edges.extend(get_prerequisite_edges(subject, valid_codes=valid_codes))

    return KnowledgeGraphOut(
        subject=subject,
        release_version=release_version,
        model_version=MODEL_VERSION,
        summary_counts=growth["summary_counts"],
        nodes=mastery_items,
        edges=edges,
    )
