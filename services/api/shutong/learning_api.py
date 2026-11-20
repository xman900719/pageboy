"""学生端智能综合练习、错题 AI 苏格拉底引导、成长状态与知识图谱 API 路由。"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import ai_tutor
from . import models as m
from . import private_files as files
from .auth import require_admin, require_student
from .database import get_db
from .guidance import (
    Evidence,
    MODEL_VERSION,
    compose_practice_plan,
    compute_knowledge_mastery,
    question_label_sort_key,
    summarize_growth,
)
from .school_paper_parser import (
    audit_reflection_with_deepseek,
    format_structured_reflection_note,
    parse_structured_reflection_note,
    validate_reflection_not_perfunctory,
)
from .schemas import (
    AdminErrorDiagnosisOut,
    AdminSelectSolutionIn,
    AdminWrongDiagnosticDetailOut,
    AdminWrongDiagnosticListItemOut,
    AdoptedSolutionOut,
    DiagnosisSolutionOptionOut,
    GrowthStatusOut,
    HistoricalWrongQuestionSummaryOut,
    KnowledgeGameConfigMapOut,
    KnowledgeGameSubjectConfigIn,
    KnowledgeGameSubjectConfigOut,
    KnowledgeGraphOut,
    PracticeQuestionPayloadOut,
    PracticeSessionCompleteOut,
    PracticeSessionCreateIn,
    PracticeSessionItemPlanOut,
    PracticeSessionOut,
    SchoolCoachDraftOut,
    SchoolCoachMessageIn,
    SchoolCoachSessionOut,
    SchoolCoachStartIn,
    SchoolCoachTurnOut,
    SchoolExamSubject,
    StudentSchoolReflectionItemOut,
    StudentSchoolReflectionsResponseOut,
    StudentSchoolReflectionSubmitIn,
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


def get_evidence(
    db: Session,
    learner_id: str,
    subject: str,
    include_school_items: bool = True,
) -> list[Evidence]:
    """收集指定学科有效客观作答证据（单知识点已审核真题；默认含已人工确认的校考逐题明细）。"""
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
    if include_school_items:
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


def _get_mapped_evidence(
    db: Session,
    learner_id: str,
    subject: str,
    valid_codes: set[str],
    include_school_items: bool = True,
    raw_evidence: list[Evidence] | None = None,
) -> list[Evidence]:
    """将作答证据中的旧/新考点编码统一映射到当前有效非选学节点。"""
    source_evidence = (
        raw_evidence
        if raw_evidence is not None
        else get_evidence(db, learner_id, subject, include_school_items=include_school_items)
    )
    mapped: list[Evidence] = []
    for ev in source_evidence:
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
    adopted_by_attempt = _load_adopted_solutions_by_attempt(db, attempt_ids)

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
                adopted_solution=adopted_by_attempt.get(att.id),
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


@router.get("/api/practice/wrong-attempts", response_model=list[HistoricalWrongQuestionSummaryOut])
def list_wrong_attempts(
    subject: Subject,
    limit: int = Query(default=20, ge=1, le=50),
    student: str = Depends(require_student),
    db: Session = Depends(get_db),
):
    """列出学生指定学科近期错题记录（含错答与正确答案对照），支持随时与「我的书童」对话复习。"""
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
    adopted_by_attempt = _load_adopted_solutions_by_attempt(db, attempt_ids)

    out: list[HistoricalWrongQuestionSummaryOut] = []
    for att, v in rows:
        codes, titles = _resolve_question_knowledge(subject, v.knowledge_ids, name_map)
        out.append(
            HistoricalWrongQuestionSummaryOut(
                attempt_id=att.id,
                question_version_id=v.id,
                subject=subject,
                stem=v.stem,
                kind=v.kind,
                options=list(v.options or []),
                student_answer=att.answer,
                correct_answer=v.correct_answer,
                earned_points=att.earned_points,
                max_points=att.max_points,
                selection_reason=None,
                knowledge_codes=codes,
                knowledge_titles=titles,
                tutor_session_id=tutor_by_attempt.get(att.id),
                adopted_solution=adopted_by_attempt.get(att.id),
                created_at=att.created_at,
            )
        )
    return out


def _decode_turn_model(model_used: str | None) -> tuple[str | None, bool]:
    if not model_used:
        return None, False
    if model_used.endswith("[guarded]"):
        raw = model_used[: -len("[guarded]")].strip()
        return (raw or None), True
    return model_used, False


def _extract_adopted_solution(diag: m.AiErrorDiagnosis) -> AdoptedSolutionOut | None:
    if not diag.selected_option_id:
        return None
    for item in list(diag.solutions or []):
        if isinstance(item, dict) and item.get("option_id") == diag.selected_option_id:
            return AdoptedSolutionOut(
                option_id=str(item["option_id"]),
                title=str(item.get("title") or ""),
                approach_focus=str(item.get("approach_focus") or ""),
                action_steps=[str(s) for s in (item.get("action_steps") or []) if str(s).strip()],
                admin_note=diag.admin_note,
                selected_at=diag.selected_at,
            )
    return None


def _load_adopted_solutions_by_attempt(
    db: Session, attempt_ids: list[str]
) -> dict[str, AdoptedSolutionOut]:
    if not attempt_ids:
        return {}
    diags = db.execute(
        select(m.AiErrorDiagnosis).where(
            m.AiErrorDiagnosis.attempt_id.in_(attempt_ids),
            m.AiErrorDiagnosis.selected_option_id.is_not(None),
        )
    ).scalars().all()
    result: dict[str, AdoptedSolutionOut] = {}
    for diag in diags:
        adopted = _extract_adopted_solution(diag)
        if adopted is not None:
            result[diag.attempt_id] = adopted
    return result


def _serialize_tutor_turns(db: Session, tutor_session_id: str) -> tuple[list[TutorTurnOut], str | None]:
    turns = db.execute(
        select(m.AiTutorTurn)
        .where(m.AiTutorTurn.tutor_session_id == tutor_session_id)
        .order_by(m.AiTutorTurn.turn_index.asc())
    ).scalars().all()
    latest_model: str | None = None
    out_turns: list[TutorTurnOut] = []
    for t in turns:
        clean_model, legacy_guarded = _decode_turn_model(t.model_used)
        if clean_model:
            latest_model = clean_model
        out_turns.append(
            TutorTurnOut(
                id=t.id,
                turn_index=t.turn_index,
                role=t.role,
                content=t.content,
                sanitized_guard_triggered=bool(t.sanitized_guard_triggered) or legacy_guarded,
                created_at=t.created_at,
            )
        )
    return out_turns, latest_model


def _serialize_tutor_session(
    db: Session,
    session_obj: m.AiTutorSession,
    stem: str,
    student_answer: str,
    knowledge_titles: list[str],
) -> TutorSessionOut:
    """序列化 AI 错题引导会话与完整对话轮次。"""
    out_turns, latest_model = _serialize_tutor_turns(db, session_obj.id)
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
            model_used=model_name,
            sanitized_guard_triggered=sanitized,
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
            sanitized_guard_triggered=False,
        )
    )
    db.add(
        m.AiTutorTurn(
            tutor_session_id=tutor_session.id,
            turn_index=next_idx + 1,
            role="assistant",
            content=reply,
            model_used=model_name,
            sanitized_guard_triggered=sanitized,
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


_GAME_SUBJECTS: tuple[Subject, ...] = ("math", "chinese", "english", "physics")


def _knowledge_game_config_path() -> Path:
    """解析当前隔离环境下知识游戏管控配置文件路径（与真实答题证据及跨环境路径物理隔离）。"""
    root = files.private_root()
    root.mkdir(parents=True, exist_ok=True)
    return root / "_knowledge_game_config.json"


def _default_subject_game_config(subject: Subject) -> dict[str, Any]:
    return {
        "subject": subject,
        "alchemy_enabled": True,
        "expedition_enabled": True,
        "initial_shields": 3,
        "prioritize_weak": True,
        "practice_gate": "recommended",
        "reset_epoch": 0,
        "updated_at": None,
    }


def _load_knowledge_game_configs() -> dict[Subject, KnowledgeGameSubjectConfigOut]:
    path = _knowledge_game_config_path()
    raw: dict[str, Any] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw = loaded
        except (OSError, json.JSONDecodeError):
            raw = {}
    out: dict[Subject, KnowledgeGameSubjectConfigOut] = {}
    for subj in _GAME_SUBJECTS:
        base = _default_subject_game_config(subj)
        entry = raw.get(subj)
        if isinstance(entry, dict):
            base.update({k: v for k, v in entry.items() if k in base})
        base["subject"] = subj
        try:
            out[subj] = KnowledgeGameSubjectConfigOut(**base)
        except Exception:
            out[subj] = KnowledgeGameSubjectConfigOut(**_default_subject_game_config(subj))
    return out


def _save_knowledge_game_configs(configs: dict[Subject, KnowledgeGameSubjectConfigOut]) -> None:
    path = _knowledge_game_config_path()
    payload = {subj: cfg.model_dump(mode="json") for subj, cfg in configs.items()}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


@router.get("/api/knowledge/game-config", response_model=KnowledgeGameConfigMapOut)
def get_student_knowledge_game_config(_student: str = Depends(require_student)):
    """学生端只读获取四科知识游戏基础管控开关与难度参数。"""
    return KnowledgeGameConfigMapOut(subjects=_load_knowledge_game_configs())


@router.get("/api/admin/knowledge/game-config", response_model=KnowledgeGameConfigMapOut)
def get_admin_knowledge_game_config(_admin: str = Depends(require_admin)):
    """管理端读取四科知识游戏基础管控开关与难度参数。"""
    return KnowledgeGameConfigMapOut(subjects=_load_knowledge_game_configs())


@router.put("/api/admin/knowledge/game-config/{subject}", response_model=KnowledgeGameSubjectConfigOut)
def update_admin_knowledge_game_config(
    subject: Subject,
    payload: KnowledgeGameSubjectConfigIn,
    _admin: str = Depends(require_admin),
):
    """管理端更新单学科知识游戏启停开关、护盾数、靶向策略或重置学生本学科游戏进度。"""
    configs = _load_knowledge_game_configs()
    prev = configs[subject]
    next_epoch = prev.reset_epoch + (1 if payload.increment_reset_epoch else 0)
    updated = KnowledgeGameSubjectConfigOut(
        subject=subject,
        alchemy_enabled=payload.alchemy_enabled,
        expedition_enabled=payload.expedition_enabled,
        initial_shields=payload.initial_shields,
        prioritize_weak=payload.prioritize_weak,
        practice_gate=payload.practice_gate,
        reset_epoch=next_epoch,
        updated_at=datetime.now(timezone.utc),
    )
    configs[subject] = updated
    _save_knowledge_game_configs(configs)
    return updated


_ETHICS_STUDENT_TOPICS = {
    "ethics.general": "道法综合主题",
    "ethics.law_citizenship": "法治与公民权利义务",
    "ethics.national_values": "家国情怀与核心价值观",
}
_SCHOOL_SUBJECTS_ORDER = ("math", "chinese", "english", "physics", "ethics")


def _resolve_reflection_subject(exam_subject: str, knowledge_id: str) -> str:
    """若场次为全科档案（all），根据知识点前缀推断单科学科。"""
    if exam_subject != "all":
        return exam_subject
    kid = str(knowledge_id or "").strip().lower()
    for prefix, subj in (
        ("math", "math"),
        ("chinese", "chinese"),
        ("english", "english"),
        ("physics", "physics"),
        ("ethics", "ethics"),
    ):
        if kid.startswith(f"{prefix}.") or kid.startswith(f"{prefix}_"):
            return subj
    return "all"


def _resolve_student_school_topic(subject: str, knowledge_id: str, name_map: dict[str, str]) -> str:
    """将校考内部知识点编码安全映射为面向学生的自然语言考点名称，绝不泄露内部编码。"""
    kid = str(knowledge_id or "").strip()
    if kid in _ETHICS_STUDENT_TOPICS:
        return _ETHICS_STUDENT_TOPICS[kid]
    if not kid or kid == "unmapped":
        return "校考待分类考点"
    if kid in name_map:
        return name_map[kid]
    mapped_codes = resolve_question_to_candidate_codes(subject, [kid])
    for code in mapped_codes:
        if code in name_map:
            return name_map[code]
    return get_topic_label(kid)


@router.get("/api/student/school-exam-reflections", response_model=StudentSchoolReflectionsResponseOut)
def list_student_school_exam_reflections(
    subject: SchoolExamSubject | None = None,
    student: str = Depends(require_student),
    db: Session = Depends(get_db),
):
    """列出学生本人已确认校考失分小题及复盘状态（严格隔离内部 knowledge_id）。"""
    rows = db.execute(
        select(m.SchoolExamItem, m.SchoolExam)
        .join(m.SchoolExam, m.SchoolExam.id == m.SchoolExamItem.school_exam_id)
        .where(
            m.SchoolExam.learner_id == student,
            m.SchoolExamItem.confirmed_by_user.is_(True),
            m.SchoolExamItem.max_points > 0,
            m.SchoolExamItem.earned_points < m.SchoolExamItem.max_points,
        )
    ).all()

    pending_counts: dict[str, int] = {sub: 0 for sub in _SCHOOL_SUBJECTS_ORDER}
    filtered_rows: list[tuple[m.SchoolExamItem, m.SchoolExam, dict]] = []

    for item, exam in rows:
        parsed = parse_structured_reflection_note(item.error_note, item.error_category, is_lost=True)
        effective_subject = _resolve_reflection_subject(exam.subject, item.knowledge_id)
        if parsed["reflection_status"] in {"pending", "needs_revision"}:
            pending_counts[effective_subject] = pending_counts.get(effective_subject, 0) + 1
        if subject is None or exam.subject == subject or effective_subject == subject or exam.subject == "all":
            filtered_rows.append((item, exam, parsed))

    nodes_cache: dict[str, tuple[list[dict], dict[str, str]]] = {}
    out_items: list[StudentSchoolReflectionItemOut] = []

    item_ids = [pair[0].id for pair in filtered_rows]
    coach_turn_counts: dict[str, int] = {}
    if item_ids:
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
        coach_turn_counts = {str(r[0]): int(r[1]) for r in cnt_rows}

    filtered_rows.sort(
        key=lambda pair: (
            -(pair[1].exam_date.toordinal() if pair[1].exam_date else 0),
            pair[1].id,
            question_label_sort_key(pair[0].question_label),
        )
    )

    for item, exam, parsed in filtered_rows:
        effective_subject = _resolve_reflection_subject(exam.subject, item.knowledge_id)
        if effective_subject not in nodes_cache:
            nodes, _ = _load_effective_knowledge_nodes(db, effective_subject)
            nodes_cache[effective_subject] = (nodes, {n["code"]: n["name"] for n in nodes})
        _nodes, name_map = nodes_cache[effective_subject]
        is_stem_confirmed = item.stem_state == "confirmed" and bool(item.stem_text)
        stem_excerpt = item.stem_text if is_stem_confirmed else None
        student_answer_excerpt = (
            item.student_answer_text if is_stem_confirmed and item.student_answer_text else None
        )

        out_items.append(
            StudentSchoolReflectionItemOut(
                item_id=item.id,
                exam_id=exam.id,
                subject=effective_subject,
                exam_title=exam.title,
                exam_date=str(exam.exam_date),
                question_label=item.question_label,
                topic=_resolve_student_school_topic(effective_subject, item.knowledge_id, name_map),
                earned_points=item.earned_points,
                max_points=item.max_points,
                lost_points=round(max(0.0, item.max_points - item.earned_points), 2),
                stem_excerpt=stem_excerpt,
                student_answer_excerpt=student_answer_excerpt,
                reflection_status=parsed["reflection_status"],
                error_category=item.error_category,
                stuck_point=parsed["stuck_point"],
                fix_strategy=parsed["fix_strategy"],
                return_reason=parsed["return_reason"],
                coach_turn_count=coach_turn_counts.get(item.id, 0),
            )
        )

    return StudentSchoolReflectionsResponseOut(
        items=out_items,
        pending_counts_by_subject=pending_counts,
        total_pending=sum(pending_counts.values()),
    )


@router.post("/api/student/school-exam-reflections/{item_id}", response_model=StudentSchoolReflectionItemOut)
def submit_student_school_exam_reflection(
    item_id: str,
    payload: StudentSchoolReflectionSubmitIn,
    student: str = Depends(require_student),
    db: Session = Depends(get_db),
):
    """学生端提交校考失分题错因分类与双栏防敷衍复盘（本地硬规则 + DeepSeek 语义把关）。"""
    item = db.get(m.SchoolExamItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")
    exam = db.get(m.SchoolExam, item.school_exam_id)
    if exam is None or exam.learner_id != student:
        raise HTTPException(status_code=404, detail="item not found")
    if not item.confirmed_by_user:
        raise HTTPException(status_code=409, detail="SCHOOL_ITEM_NOT_CONFIRMED")
    if item.earned_points >= item.max_points:
        raise HTTPException(status_code=422, detail="FULL_SCORE_ITEM_HAS_NO_ERROR_CATEGORY")

    # Stage 1: 本地反敷衍硬规则校验
    local_err = validate_reflection_not_perfunctory(payload.stuck_point, payload.fix_strategy)
    if local_err is not None:
        raise HTTPException(status_code=422, detail=f"REFLECTION_TOO_PERFUNCTORY: {local_err}")

    effective_subject = _resolve_reflection_subject(exam.subject, item.knowledge_id)
    nodes, _ = _load_effective_knowledge_nodes(db, effective_subject)
    name_map = {n["code"]: n["name"] for n in nodes}
    topic = _resolve_student_school_topic(effective_subject, item.knowledge_id, name_map)
    is_stem_confirmed = item.stem_state == "confirmed" and bool(item.stem_text)
    stem_excerpt = item.stem_text if is_stem_confirmed else None
    student_answer_excerpt = (
        item.student_answer_text if is_stem_confirmed and item.student_answer_text else None
    )

    # Stage 2: DeepSeek 语义审阅官把关（未配置或超时时平滑降级为本地严规放行）
    passed, coach_feedback, audit_mode = audit_reflection_with_deepseek(
        subject=effective_subject,
        topic=topic,
        question_label=item.question_label,
        stem_excerpt=stem_excerpt,
        error_category=payload.error_category,
        stuck_point=payload.stuck_point,
        fix_strategy=payload.fix_strategy,
    )
    if not passed:
        raise HTTPException(
            status_code=422,
            detail=f"REFLECTION_AI_COACH_REJECTED: {coach_feedback or '请进一步补充具体出错步骤与改进对策。'}",
        )

    item.error_category = payload.error_category
    item.error_note = format_structured_reflection_note(payload.stuck_point, payload.fix_strategy)
    db.commit()
    db.refresh(item)

    parsed = parse_structured_reflection_note(item.error_note, item.error_category, is_lost=True)
    return StudentSchoolReflectionItemOut(
        item_id=item.id,
        exam_id=exam.id,
        subject=effective_subject,
        exam_title=exam.title,
        exam_date=str(exam.exam_date),
        question_label=item.question_label,
        topic=topic,
        earned_points=item.earned_points,
        max_points=item.max_points,
        lost_points=round(max(0.0, item.max_points - item.earned_points), 2),
        stem_excerpt=stem_excerpt,
        student_answer_excerpt=student_answer_excerpt,
        reflection_status=parsed["reflection_status"],
        error_category=item.error_category,
        stuck_point=parsed["stuck_point"],
        fix_strategy=parsed["fix_strategy"],
        return_reason=parsed["return_reason"],
        ai_audit_mode=audit_mode,
    )


_SCHOOL_COACH_MAX_USER_TURNS = 12


def _load_owned_lost_school_item(
    db: Session, item_id: str, learner_id: str
) -> tuple[m.SchoolExamItem, m.SchoolExam, str]:
    """校验归属且必须为已确认失分小题，同时安全映射自然语言考点（绝不泄露内部编码）。"""
    item = db.get(m.SchoolExamItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")
    exam = db.get(m.SchoolExam, item.school_exam_id)
    if exam is None or exam.learner_id != learner_id:
        raise HTTPException(status_code=404, detail="item not found")
    if not item.confirmed_by_user:
        raise HTTPException(status_code=409, detail="SCHOOL_ITEM_NOT_CONFIRMED")
    if item.earned_points >= item.max_points:
        raise HTTPException(status_code=422, detail="FULL_SCORE_ITEM_HAS_NO_ERROR_CATEGORY")
    effective_subject = _resolve_reflection_subject(exam.subject, item.knowledge_id)
    nodes, _ = _load_effective_knowledge_nodes(db, effective_subject)
    name_map = {n["code"]: n["name"] for n in nodes}
    topic = _resolve_student_school_topic(effective_subject, item.knowledge_id, name_map)
    return item, exam, topic


def serialize_school_coach_session(
    db: Session,
    item_id: str,
    session_obj: m.SchoolReflectionCoachSession | None,
) -> SchoolCoachSessionOut:
    """序列化校考「书童陪你想」会话状态与历史轮次。"""
    if session_obj is None:
        return SchoolCoachSessionOut(
            id=None,
            item_id=item_id,
            started=False,
            status="inactive",
            user_turn_count=0,
            max_user_turns=_SCHOOL_COACH_MAX_USER_TURNS,
            can_summarize=False,
            draft_summary=None,
            turns=[],
        )
    turns = db.execute(
        select(m.SchoolReflectionCoachTurn)
        .where(m.SchoolReflectionCoachTurn.session_id == session_obj.id)
        .order_by(m.SchoolReflectionCoachTurn.turn_index.asc())
    ).scalars().all()
    user_turns = [t for t in turns if t.role == "user"]
    effective_user_chars = sum(len(re.findall(r"[\u4e00-\u9fffA-Za-z]", t.content or "")) for t in user_turns)
    draft_obj: SchoolCoachDraftOut | None = None
    if isinstance(session_obj.draft_summary, dict):
        raw_cat = session_obj.draft_summary.get("error_category")
        draft_obj = SchoolCoachDraftOut(
            error_category=raw_cat if raw_cat in {"concept", "calculation", "reading", "method", "norm", "other"} else None,
            stuck_point=str(session_obj.draft_summary.get("stuck_point") or ""),
            fix_strategy=str(session_obj.draft_summary.get("fix_strategy") or ""),
            ready=bool(session_obj.draft_summary.get("ready")),
        )
    return SchoolCoachSessionOut(
        id=session_obj.id,
        item_id=item_id,
        started=len(turns) > 0,
        status=session_obj.status,
        user_turn_count=len(user_turns),
        max_user_turns=_SCHOOL_COACH_MAX_USER_TURNS,
        can_summarize=len(user_turns) >= 2 and effective_user_chars >= 10,
        draft_summary=draft_obj,
        turns=[
            SchoolCoachTurnOut(
                id=t.id,
                turn_index=t.turn_index,
                role="assistant" if t.role == "assistant" else "user",
                content=t.content,
                model_used=t.model_used,
                sanitized_guard_triggered=bool(t.sanitized_guard_triggered),
                created_at=t.created_at.isoformat() if t.created_at else "",
            )
            for t in turns
        ],
    )


@router.get("/api/student/school-exam-reflections/{item_id}/coach", response_model=SchoolCoachSessionOut)
def get_student_school_reflection_coach(
    item_id: str,
    student: str = Depends(require_student),
    db: Session = Depends(get_db),
):
    """只读读取校考失分题的「书童陪你想」历史对话（零 AI 调用）。"""
    _load_owned_lost_school_item(db, item_id, student)
    session_obj = db.execute(
        select(m.SchoolReflectionCoachSession).where(
            m.SchoolReflectionCoachSession.school_exam_item_id == item_id,
            m.SchoolReflectionCoachSession.learner_id == student,
        )
    ).scalar_one_or_none()
    return serialize_school_coach_session(db, item_id, session_obj)


@router.post("/api/student/school-exam-reflections/{item_id}/coach/start", response_model=SchoolCoachSessionOut)
def start_student_school_reflection_coach(
    item_id: str,
    payload: SchoolCoachStartIn | None = None,
    student: str = Depends(require_student),
    db: Session = Depends(get_db),
):
    """幂等开启「书童陪你想」对话；若已有轮次则直接恢复，绝不重复调用 AI。"""
    item, exam, topic = _load_owned_lost_school_item(db, item_id, student)
    session_obj = db.execute(
        select(m.SchoolReflectionCoachSession).where(
            m.SchoolReflectionCoachSession.school_exam_item_id == item_id,
            m.SchoolReflectionCoachSession.learner_id == student,
        )
    ).scalar_one_or_none()

    if session_obj is not None:
        existing_out = serialize_school_coach_session(db, item_id, session_obj)
        if existing_out.started:
            return existing_out

    is_stem_confirmed = item.stem_state == "confirmed" and bool(item.stem_text)
    confirmed_stem = item.stem_text if is_stem_confirmed else None
    confirmed_ans = item.student_answer_text if (is_stem_confirmed and item.student_answer_text) else None
    scene_hint = payload.scene_hint if payload else None

    system_prompt = ai_tutor.build_school_reflection_coach_prompt(
        subject=exam.subject,
        topic=topic,
        question_label=item.question_label,
        earned_points=item.earned_points,
        max_points=item.max_points,
        stem_text=confirmed_stem,
        student_answer_text=confirmed_ans,
        scene_hint=scene_hint,
    )
    opener_trigger = (
        "请用温和自然的口吻向学生打个招呼，结合题目与考点提出第 1 个容易回答的小问题，陪他开始复盘这道题。"
        if confirmed_stem
        else "当前系统尚未录入原卷题干，请温和向学生打招呼并说明你暂时看不到原题，请他先用一句话说说这题考什么、当时第一步是怎么想的。"
    )
    try:
        reply_text, guard_triggered, model_used = ai_tutor.request_school_reflection_coach_reply(
            system_prompt=system_prompt,
            history_turns=[{"role": "user", "content": opener_trigger}],
            topic=topic,
            has_stem=bool(confirmed_stem),
        )
    except ai_tutor.AiTutorConfigError as exc:
        raise HTTPException(status_code=503, detail="COACH_NOT_CONFIGURED") from exc
    except ai_tutor.AiTutorUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"COACH_UNAVAILABLE: {exc}") from exc

    if session_obj is None:
        session_obj = m.SchoolReflectionCoachSession(
            learner_id=student,
            school_exam_item_id=item_id,
            status="active",
        )
        db.add(session_obj)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            existing = db.execute(
                select(m.SchoolReflectionCoachSession).where(
                    m.SchoolReflectionCoachSession.school_exam_item_id == item_id,
                    m.SchoolReflectionCoachSession.learner_id == student,
                )
            ).scalar_one_or_none()
            return serialize_school_coach_session(db, item_id, existing)

    db.add(
        m.SchoolReflectionCoachTurn(
            session_id=session_obj.id,
            turn_index=0,
            role="assistant",
            content=reply_text,
            model_used=model_used,
            sanitized_guard_triggered=guard_triggered,
        )
    )
    session_obj.updated_at = m.now()
    db.commit()
    return serialize_school_coach_session(db, item_id, session_obj)


@router.post("/api/student/school-exam-reflections/{item_id}/coach/message", response_model=SchoolCoachSessionOut)
def send_student_school_reflection_coach_message(
    item_id: str,
    payload: SchoolCoachMessageIn,
    student: str = Depends(require_student),
    db: Session = Depends(get_db),
):
    """学生在「书童陪你想」中追加一条发言，返回书童最新引导追问（单题上限 12 轮用户发言）。"""
    item, exam, topic = _load_owned_lost_school_item(db, item_id, student)
    session_obj = db.execute(
        select(m.SchoolReflectionCoachSession).where(
            m.SchoolReflectionCoachSession.school_exam_item_id == item_id,
            m.SchoolReflectionCoachSession.learner_id == student,
        )
    ).scalar_one_or_none()
    if session_obj is None:
        session_obj = m.SchoolReflectionCoachSession(
            learner_id=student,
            school_exam_item_id=item_id,
            status="active",
        )
        db.add(session_obj)
        db.flush()

    existing_turns = db.execute(
        select(m.SchoolReflectionCoachTurn)
        .where(m.SchoolReflectionCoachTurn.session_id == session_obj.id)
        .order_by(m.SchoolReflectionCoachTurn.turn_index.asc())
    ).scalars().all()
    user_turn_count = sum(1 for t in existing_turns if t.role == "user")
    if user_turn_count >= _SCHOOL_COACH_MAX_USER_TURNS:
        raise HTTPException(status_code=409, detail="COACH_TURN_LIMIT_REACHED")

    is_stem_confirmed = item.stem_state == "confirmed" and bool(item.stem_text)
    confirmed_stem = item.stem_text if is_stem_confirmed else None
    confirmed_ans = item.student_answer_text if (is_stem_confirmed and item.student_answer_text) else None

    system_prompt = ai_tutor.build_school_reflection_coach_prompt(
        subject=exam.subject,
        topic=topic,
        question_label=item.question_label,
        earned_points=item.earned_points,
        max_points=item.max_points,
        stem_text=confirmed_stem,
        student_answer_text=confirmed_ans,
    )
    history = [{"role": t.role, "content": t.content} for t in existing_turns]
    history.append({"role": "user", "content": payload.content})

    try:
        reply_text, guard_triggered, model_used = ai_tutor.request_school_reflection_coach_reply(
            system_prompt=system_prompt,
            history_turns=history,
            topic=topic,
            has_stem=bool(confirmed_stem),
        )
    except ai_tutor.AiTutorConfigError as exc:
        raise HTTPException(status_code=503, detail="COACH_NOT_CONFIGURED") from exc
    except ai_tutor.AiTutorUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"COACH_UNAVAILABLE: {exc}") from exc

    next_index = (existing_turns[-1].turn_index + 1) if existing_turns else 0
    db.add(
        m.SchoolReflectionCoachTurn(
            session_id=session_obj.id,
            turn_index=next_index,
            role="user",
            content=payload.content,
        )
    )
    db.add(
        m.SchoolReflectionCoachTurn(
            session_id=session_obj.id,
            turn_index=next_index + 1,
            role="assistant",
            content=reply_text,
            model_used=model_used,
            sanitized_guard_triggered=guard_triggered,
        )
    )
    session_obj.updated_at = m.now()
    db.commit()
    return serialize_school_coach_session(db, item_id, session_obj)


@router.post("/api/student/school-exam-reflections/{item_id}/coach/summarize", response_model=SchoolCoachSessionOut)
def summarize_student_school_reflection_coach(
    item_id: str,
    student: str = Depends(require_student),
    db: Session = Depends(get_db),
):
    """基于学生真实对话忠实整理提醒卡草稿（至少 2 轮学生发言，绝不自动提交复盘）。"""
    item, exam, topic = _load_owned_lost_school_item(db, item_id, student)
    session_obj = db.execute(
        select(m.SchoolReflectionCoachSession).where(
            m.SchoolReflectionCoachSession.school_exam_item_id == item_id,
            m.SchoolReflectionCoachSession.learner_id == student,
        )
    ).scalar_one_or_none()
    if session_obj is None:
        raise HTTPException(status_code=422, detail="COACH_DIALOGUE_TOO_SHORT")

    turns = db.execute(
        select(m.SchoolReflectionCoachTurn)
        .where(m.SchoolReflectionCoachTurn.session_id == session_obj.id)
        .order_by(m.SchoolReflectionCoachTurn.turn_index.asc())
    ).scalars().all()
    user_turns = [t for t in turns if t.role == "user"]
    effective_user_chars = sum(len(re.findall(r"[\u4e00-\u9fffA-Za-z]", t.content or "")) for t in user_turns)
    if len(user_turns) < 2 or effective_user_chars < 10:
        raise HTTPException(status_code=422, detail="COACH_DIALOGUE_TOO_SHORT")

    try:
        summary, _model_used = ai_tutor.request_school_reflection_summary(
            subject=exam.subject,
            topic=topic,
            question_label=item.question_label,
            dialogue_turns=[{"role": t.role, "content": t.content} for t in turns],
        )
    except ai_tutor.AiTutorConfigError as exc:
        raise HTTPException(status_code=503, detail="COACH_NOT_CONFIGURED") from exc
    except ai_tutor.AiTutorUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"COACH_UNAVAILABLE: {exc}") from exc

    session_obj.draft_summary = summary
    session_obj.status = "summarized"
    session_obj.updated_at = m.now()
    db.commit()
    return serialize_school_coach_session(db, item_id, session_obj)


def _serialize_admin_diagnosis(diag: m.AiErrorDiagnosis | None) -> AdminErrorDiagnosisOut | None:
    if diag is None:
        return None
    return AdminErrorDiagnosisOut(
        id=diag.id,
        attempt_id=diag.attempt_id,
        tutor_session_id=diag.tutor_session_id,
        root_cause_summary=diag.root_cause_summary,
        cognitive_gap_type=diag.cognitive_gap_type,
        evidence_from_dialogue=diag.evidence_from_dialogue,
        solutions=[
            DiagnosisSolutionOptionOut(
                option_id=item["option_id"],
                title=item["title"],
                approach_focus=item["approach_focus"],
                rationale=item["rationale"],
                action_steps=list(item.get("action_steps") or []),
            )
            for item in (diag.solutions or [])
            if isinstance(item, dict)
        ],
        selected_option_id=diag.selected_option_id,
        admin_note=diag.admin_note,
        model_used=diag.model_used,
        created_at=diag.created_at,
        updated_at=diag.updated_at,
        selected_at=diag.selected_at,
    )


def _load_admin_wrong_attempt(
    db: Session, owner: str, attempt_id: str
) -> tuple[m.AnswerAttempt, m.QuestionVersion, m.Question, list[str], list[str]]:
    att = db.get(m.AnswerAttempt, attempt_id)
    if att is None or att.learner_id != owner:
        raise HTTPException(status_code=404, detail="attempt not found")
    v = db.get(m.QuestionVersion, att.question_version_id)
    q = db.get(m.Question, v.question_id) if v is not None else None
    if v is None or q is None:
        raise HTTPException(status_code=404, detail="question version not found")
    if att.earned_points is None or att.earned_points >= att.max_points:
        raise HTTPException(status_code=422, detail="ATTEMPT_NOT_WRONG")
    nodes, _ = _load_effective_knowledge_nodes(db, q.subject)
    name_map = {n["code"]: n["name"] for n in nodes}
    codes, titles = _resolve_question_knowledge(q.subject, v.knowledge_ids, name_map)
    return att, v, q, codes, titles


def _build_admin_wrong_detail(
    db: Session,
    att: m.AnswerAttempt,
    v: m.QuestionVersion,
    q: m.Question,
    codes: list[str],
    titles: list[str],
) -> AdminWrongDiagnosticDetailOut:
    tutor_session = db.execute(
        select(m.AiTutorSession).where(
            m.AiTutorSession.attempt_id == att.id,
            m.AiTutorSession.learner_id == att.learner_id,
        )
    ).scalar_one_or_none()
    tutor_turns: list[TutorTurnOut] = []
    if tutor_session is not None:
        tutor_turns, _ = _serialize_tutor_turns(db, tutor_session.id)
    diag = db.execute(
        select(m.AiErrorDiagnosis).where(m.AiErrorDiagnosis.attempt_id == att.id)
    ).scalar_one_or_none()
    return AdminWrongDiagnosticDetailOut(
        attempt_id=att.id,
        question_version_id=v.id,
        subject=q.subject,
        stem=v.stem,
        kind=v.kind,
        options=list(v.options or []),
        correct_answer=v.correct_answer,
        student_answer=att.answer,
        earned_points=att.earned_points,
        max_points=att.max_points,
        knowledge_codes=codes,
        knowledge_titles=titles,
        tutor_session_id=tutor_session.id if tutor_session is not None else None,
        tutor_turns=tutor_turns,
        diagnosis=_serialize_admin_diagnosis(diag),
        created_at=att.created_at,
    )


def _safe_stem_excerpt(stem: str, max_len: int = 88) -> str:
    """生成题干摘要时避免从 $...$ / $$...$$ 公式内部截断，防止前端渲染出未闭合 LaTeX。"""
    clean = re.sub(r"\s+", " ", stem or "").strip()
    if len(clean) <= max_len:
        return clean

    in_math = False
    delim_len = 1
    i = 0
    cut_pos = max_len
    while i < len(clean):
        if clean[i] == "$":
            is_double = i + 1 < len(clean) and clean[i + 1] == "$"
            step = 2 if is_double else 1
            if not in_math:
                in_math = True
                delim_len = step
                i += step
                continue
            if step == delim_len or (delim_len == 1 and not is_double):
                in_math = False
                i += step
                if i >= max_len:
                    cut_pos = i
                    break
                continue
        i += 1
        if not in_math and i >= max_len:
            cut_pos = i
            break
    else:
        cut_pos = len(clean)

    return f"{clean[:cut_pos]}…" if cut_pos < len(clean) else clean


@router.get("/api/admin/wrong-diagnostics", response_model=list[AdminWrongDiagnosticListItemOut])
def list_admin_wrong_diagnostics(
    subject: Subject,
    limit: int = Query(default=20, ge=1, le=50),
    admin: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """管理端：列出指定学科近期错题及关联的 AI 引导对话轮次、AI 错因诊断与采纳状态。"""
    nodes, _ = _load_effective_knowledge_nodes(db, subject)
    name_map = {n["code"]: n["name"] for n in nodes}

    rows = db.execute(
        select(m.AnswerAttempt, m.QuestionVersion)
        .join(m.QuestionVersion, m.QuestionVersion.id == m.AnswerAttempt.question_version_id)
        .join(m.Question, m.Question.id == m.QuestionVersion.question_id)
        .where(
            m.AnswerAttempt.learner_id == admin,
            m.Question.subject == subject,
            m.AnswerAttempt.earned_points.is_not(None),
            m.AnswerAttempt.earned_points < m.AnswerAttempt.max_points,
        )
        .order_by(m.AnswerAttempt.created_at.desc(), m.AnswerAttempt.id.desc())
        .limit(limit)
    ).all()

    attempt_ids = [a.id for a, _ in rows]
    tutor_by_attempt: dict[str, m.AiTutorSession] = {}
    turn_counts: dict[str, int] = {}
    diag_by_attempt: dict[str, m.AiErrorDiagnosis] = {}

    if attempt_ids:
        sessions = db.execute(
            select(m.AiTutorSession).where(m.AiTutorSession.attempt_id.in_(attempt_ids))
        ).scalars().all()
        session_ids = [s.id for s in sessions]
        for s in sessions:
            tutor_by_attempt[s.attempt_id] = s
        if session_ids:
            for sid, cnt in db.execute(
                select(m.AiTutorTurn.tutor_session_id, func.count())
                .where(m.AiTutorTurn.tutor_session_id.in_(session_ids))
                .group_by(m.AiTutorTurn.tutor_session_id)
            ).all():
                turn_counts[sid] = int(cnt)
        for d in db.execute(
            select(m.AiErrorDiagnosis).where(m.AiErrorDiagnosis.attempt_id.in_(attempt_ids))
        ).scalars().all():
            diag_by_attempt[d.attempt_id] = d

    out: list[AdminWrongDiagnosticListItemOut] = []
    for att, v in rows:
        codes, titles = _resolve_question_knowledge(subject, v.knowledge_ids, name_map)
        ts = tutor_by_attempt.get(att.id)
        diag = diag_by_attempt.get(att.id)
        adopted = _extract_adopted_solution(diag) if diag is not None else None
        excerpt = _safe_stem_excerpt(v.stem or "", max_len=88)
        out.append(
            AdminWrongDiagnosticListItemOut(
                attempt_id=att.id,
                question_version_id=v.id,
                subject=subject,
                stem_excerpt=excerpt,
                kind=v.kind,
                options=list(v.options or []),
                correct_answer=v.correct_answer,
                student_answer=att.answer,
                earned_points=att.earned_points,
                max_points=att.max_points,
                knowledge_codes=codes,
                knowledge_titles=titles,
                tutor_session_id=ts.id if ts is not None else None,
                tutor_turn_count=turn_counts.get(ts.id, 0) if ts is not None else 0,
                has_diagnosis=diag is not None,
                selected_option_id=diag.selected_option_id if diag is not None else None,
                selected_solution_title=adopted.title if adopted is not None else None,
                cognitive_gap_type=diag.cognitive_gap_type if diag is not None else None,
                created_at=att.created_at,
            )
        )
    return out


@router.get("/api/admin/wrong-diagnostics/{attempt_id}", response_model=AdminWrongDiagnosticDetailOut)
def get_admin_wrong_diagnostic_detail(
    attempt_id: str,
    admin: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """管理端：读取单道错题的标准答案、完整数据库引导对话回放与 AI 错因诊断结果。"""
    att, v, q, codes, titles = _load_admin_wrong_attempt(db, admin, attempt_id)
    return _build_admin_wrong_detail(db, att, v, q, codes, titles)


@router.post("/api/admin/wrong-diagnostics/{attempt_id}/analyze", response_model=AdminWrongDiagnosticDetailOut)
def analyze_admin_wrong_diagnostic(
    attempt_id: str,
    admin: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """管理端：手动触发 AI 结合错题与持久化引导对话，剖析真正错因并生成 3 个可选解决方法。"""
    att, v, q, codes, titles = _load_admin_wrong_attempt(db, admin, attempt_id)
    tutor_session = db.execute(
        select(m.AiTutorSession).where(
            m.AiTutorSession.attempt_id == att.id,
            m.AiTutorSession.learner_id == admin,
        )
    ).scalar_one_or_none()

    dialogue_turns: list[dict[str, str]] = []
    if tutor_session is not None:
        turns = db.execute(
            select(m.AiTutorTurn)
            .where(m.AiTutorTurn.tutor_session_id == tutor_session.id)
            .order_by(m.AiTutorTurn.turn_index.asc())
        ).scalars().all()
        dialogue_turns = [{"role": t.role, "content": t.content} for t in turns]

    try:
        parsed, model_used = ai_tutor.request_error_root_cause_analysis(
            subject=q.subject,
            stem=v.stem,
            choices=list(v.options or []),
            correct_answer=v.correct_answer,
            student_answer=att.answer,
            knowledge_titles=titles,
            dialogue_turns=dialogue_turns,
        )
    except (ai_tutor.AiTutorConfigError, ai_tutor.AiTutorUnavailableError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    now_dt = datetime.now(timezone.utc)
    diag = db.execute(
        select(m.AiErrorDiagnosis).where(m.AiErrorDiagnosis.attempt_id == att.id)
    ).scalar_one_or_none()
    if diag is None:
        diag = m.AiErrorDiagnosis(
            learner_id=admin,
            attempt_id=att.id,
            tutor_session_id=tutor_session.id if tutor_session is not None else None,
            question_version_id=v.id,
            subject=q.subject,
            root_cause_summary=parsed["root_cause_summary"],
            cognitive_gap_type=parsed["cognitive_gap_type"],
            evidence_from_dialogue=parsed["evidence_from_dialogue"],
            solutions=parsed["solutions"],
            model_used=model_used,
            created_at=now_dt,
            updated_at=now_dt,
        )
        db.add(diag)
    else:
        diag.tutor_session_id = tutor_session.id if tutor_session is not None else None
        diag.root_cause_summary = parsed["root_cause_summary"]
        diag.cognitive_gap_type = parsed["cognitive_gap_type"]
        diag.evidence_from_dialogue = parsed["evidence_from_dialogue"]
        diag.solutions = parsed["solutions"]
        diag.selected_option_id = None
        diag.selected_at = None
        diag.model_used = model_used
        diag.updated_at = now_dt

    db.commit()
    return _build_admin_wrong_detail(db, att, v, q, codes, titles)


@router.post(
    "/api/admin/wrong-diagnostics/{attempt_id}/select-solution",
    response_model=AdminWrongDiagnosticDetailOut,
)
def select_admin_wrong_diagnostic_solution(
    attempt_id: str,
    payload: AdminSelectSolutionIn,
    admin: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """管理端：从 AI 给出的 3 个解决对策中选定 1 项并保存备注（Level 2 联动学生端展示）。"""
    att, v, q, codes, titles = _load_admin_wrong_attempt(db, admin, attempt_id)
    diag = db.execute(
        select(m.AiErrorDiagnosis).where(m.AiErrorDiagnosis.attempt_id == att.id)
    ).scalar_one_or_none()
    if diag is None:
        raise HTTPException(status_code=404, detail="DIAGNOSIS_NOT_FOUND")

    valid_ids = {
        str(item.get("option_id"))
        for item in (diag.solutions or [])
        if isinstance(item, dict)
    }
    if payload.option_id not in valid_ids:
        raise HTTPException(status_code=422, detail="INVALID_SOLUTION_OPTION")

    now_dt = datetime.now(timezone.utc)
    diag.selected_option_id = payload.option_id
    diag.admin_note = payload.admin_note.strip() if payload.admin_note and payload.admin_note.strip() else None
    diag.selected_at = now_dt
    diag.updated_at = now_dt
    db.commit()
    return _build_admin_wrong_detail(db, att, v, q, codes, titles)
