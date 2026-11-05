"""四科语料增量接口：知识点版本化与双向关联、真题连续性、命题研究与回测。组合复用现有 owner 鉴权与模型。"""
from __future__ import annotations
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from . import models as m
from .auth import require_owner
from .database import get_db
from .research import RULE_VERSION, coverage_report, statistics, backtest, predict
from .schemas import Subject

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_owner)])


class NodeIn(BaseModel):
    subject: Subject
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    parent_code: str | None = None
    origin: Literal["manual", "ai_suggested"] = "manual"


class NodeVersionIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class LinkIn(BaseModel):
    question_version_id: str
    node_id: str
    sub_index: int = Field(default=0, ge=0)
    role: Literal["core", "aux"] = "core"
    evidence: str | None = None


class ErratumIn(BaseModel):
    note: str = Field(min_length=1)


class RunIn(BaseModel):
    subject: Subject
    target_year: int = Field(ge=2000, le=2100)


def _latest(db: Session, node_id: str) -> m.KnowledgeNodeVersion:
    return db.scalars(select(m.KnowledgeNodeVersion).where(m.KnowledgeNodeVersion.node_id == node_id).order_by(m.KnowledgeNodeVersion.version.desc())).first()


@router.post("/knowledge/nodes", status_code=201)
def create_node(p: NodeIn, db: Session = Depends(get_db)):
    if db.scalar(select(m.KnowledgeNode).where(m.KnowledgeNode.code == p.code)):
        raise HTTPException(409, detail="KNOWLEDGE_CODE_EXISTS")
    parent_id = None
    if p.parent_code:
        parent = db.scalar(select(m.KnowledgeNode).where(m.KnowledgeNode.code == p.parent_code))
        if parent is None or parent.subject != p.subject:
            raise HTTPException(422, detail="PARENT_INVALID")
        parent_id = parent.id
    node = m.KnowledgeNode(subject=p.subject, code=p.code, parent_id=parent_id)
    db.add(node); db.flush()
    db.add(m.KnowledgeNodeVersion(node_id=node.id, version=1, name=p.name, description=p.description, origin=p.origin))
    db.commit()
    return {"id": node.id, "code": node.code, "version": 1}


@router.post("/knowledge/nodes/{node_id}/versions", status_code=201)
def revise_node(node_id: str, p: NodeVersionIn, db: Session = Depends(get_db)):
    node = db.get(m.KnowledgeNode, node_id)
    if node is None:
        raise HTTPException(404, detail="node not found")
    if node.status != "active":
        raise HTTPException(409, detail="NODE_NOT_ACTIVE")
    nxt = _latest(db, node_id).version + 1
    db.add(m.KnowledgeNodeVersion(node_id=node_id, version=nxt, name=p.name, description=p.description))
    db.commit()
    return {"id": node_id, "version": nxt}


@router.post("/knowledge/nodes/{node_id}/deprecate")
def deprecate_node(node_id: str, merged_into: str | None = None, db: Session = Depends(get_db)):
    node = db.get(m.KnowledgeNode, node_id)
    if node is None:
        raise HTTPException(404, detail="node not found")
    if merged_into:
        target = db.get(m.KnowledgeNode, merged_into)
        if target is None or target.subject != node.subject or target.id == node.id:
            raise HTTPException(422, detail="MERGE_TARGET_INVALID")
        node.merged_into_id = target.id
        node.status = "merged"
    else:
        node.status = "deprecated"
    db.commit()  # 既有关联行保持原 node_version，不被改写
    return {"id": node.id, "status": node.status}


@router.post("/knowledge/links", status_code=201)
def link(p: LinkIn, db: Session = Depends(get_db)):
    qv = db.get(m.QuestionVersion, p.question_version_id)
    node = db.get(m.KnowledgeNode, p.node_id)
    if qv is None or node is None:
        raise HTTPException(404, detail="question version or node not found")
    q = db.get(m.Question, qv.question_id)
    if q.subject != node.subject:
        raise HTTPException(422, detail="SUBJECT_MISMATCH")
    if node.status != "active":
        raise HTTPException(409, detail="NODE_NOT_ACTIVE")
    exists = db.scalar(select(m.QuestionKnowledgeLink).where(m.QuestionKnowledgeLink.question_version_id == qv.id, m.QuestionKnowledgeLink.sub_index == p.sub_index, m.QuestionKnowledgeLink.node_id == node.id))
    if exists:
        raise HTTPException(409, detail="LINK_EXISTS")
    row = m.QuestionKnowledgeLink(question_version_id=qv.id, sub_index=p.sub_index, node_id=node.id, node_version=_latest(db, node.id).version, role=p.role, evidence=p.evidence)
    db.add(row); db.commit()
    return {"id": row.id, "node_version": row.node_version, "review_status": row.review_status}


@router.post("/knowledge/links/{link_id}/review")
def review_link(link_id: str, db: Session = Depends(get_db)):
    row = db.get(m.QuestionKnowledgeLink, link_id)
    if row is None:
        raise HTTPException(404, detail="link not found")
    row.review_status = "approved"; db.commit()
    return {"id": row.id, "review_status": row.review_status}


@router.get("/knowledge/nodes/{node_id}/questions")
def node_questions(node_id: str, db: Session = Depends(get_db)):
    rows = db.scalars(select(m.QuestionKnowledgeLink).where(m.QuestionKnowledgeLink.node_id == node_id)).all()
    return [{"question_version_id": r.question_version_id, "sub_index": r.sub_index, "role": r.role, "node_version": r.node_version, "review_status": r.review_status} for r in rows]


@router.get("/questions/{version_id}/knowledge")
def question_knowledge(version_id: str, db: Session = Depends(get_db)):
    rows = db.scalars(select(m.QuestionKnowledgeLink).where(m.QuestionKnowledgeLink.question_version_id == version_id)).all()
    return [{"node_id": r.node_id, "node_version": r.node_version, "sub_index": r.sub_index, "role": r.role, "evidence": r.evidence, "review_status": r.review_status} for r in rows]


@router.post("/questions/{version_id}/errata", status_code=201)
def add_erratum(version_id: str, p: ErratumIn, db: Session = Depends(get_db)):
    if db.get(m.QuestionVersion, version_id) is None:
        raise HTTPException(404, detail="version not found")
    row = m.Erratum(question_version_id=version_id, note=p.note)
    db.add(row); db.commit()
    return {"id": row.id}  # 勘误只追加，原题内容不变


@router.get("/coverage")
def coverage(year_from: int = 2018, year_to: int = 2026, db: Session = Depends(get_db)):
    docs = []
    for s in db.scalars(select(m.SourceDocument).where(m.SourceDocument.source_class == "official_exam", m.SourceDocument.exam_year.is_not(None))):
        # 采录进度按逻辑题去重；草稿题仍属于已采录题，不等于审核通过。
        count = db.scalar(
            select(func.count(func.distinct(m.Question.id)))
            .join(m.QuestionVersion, m.QuestionVersion.question_id == m.Question.id)
            .where(m.Question.source_document_id == s.id)
        )
        # 存在经人工审核的已发布版本才算质量审核通过；新草稿不覆盖旧发布版。
        reviewed_count = db.scalar(
            select(func.count(func.distinct(m.Question.id)))
            .join(m.QuestionVersion, m.QuestionVersion.question_id == m.Question.id)
            .where(
                m.Question.source_document_id == s.id,
                m.QuestionVersion.status == "published",
                m.QuestionVersion.reviewed_by_human.is_(True),
            )
        )
        # 重复原件检测只使用服务端上传生成的附件哈希，不使用历史手填的来源哈希。
        first_hash = db.scalar(
            select(m.SourceAttachment.sha256)
            .where(m.SourceAttachment.source_document_id == s.id)
            .order_by(m.SourceAttachment.created_at, m.SourceAttachment.id)
            .limit(1)
        )
        docs.append({"id": s.id, "subject": s.subject, "exam_year": s.exam_year, "sha256": first_hash, "ingest_status": s.ingest_status, "verified": s.verified, "review_status": s.review_status, "question_count": count, "reviewed_question_count": reviewed_count})
    return coverage_report(docs, year_from, year_to)


def _official_rows(db: Session, subject: str) -> list[dict]:
    """只统计已验证、已审核官方来源下每道题最新的人工审核发布版。

    仅采用已审核通过的知识点关联；已发布但尚未审核知识点关联的题目
    仍可进入题量及题型统计，其 knowledge 为空。
    """
    latest_published = (
        select(
            m.QuestionVersion.question_id,
            func.max(m.QuestionVersion.version).label("version"),
        )
        .where(
            m.QuestionVersion.status == "published",
            m.QuestionVersion.reviewed_by_human.is_(True),
        )
        .group_by(m.QuestionVersion.question_id)
        .subquery()
    )
    q = (
        select(m.QuestionVersion, m.SourceDocument)
        .join(m.Question, m.Question.id == m.QuestionVersion.question_id)
        .join(m.SourceDocument, m.SourceDocument.id == m.Question.source_document_id)
        .join(
            latest_published,
            (m.QuestionVersion.question_id == latest_published.c.question_id)
            & (m.QuestionVersion.version == latest_published.c.version),
        )
        .where(
            m.SourceDocument.source_class == "official_exam",
            m.SourceDocument.subject == subject,
            m.SourceDocument.exam_year.is_not(None),
            m.SourceDocument.verified.is_(True),
            m.SourceDocument.review_status == "approved",
            m.QuestionVersion.status == "published",
            m.QuestionVersion.reviewed_by_human.is_(True),
        )
    )
    out = []
    for qv, src in db.execute(q):
        codes = db.scalars(
            select(m.KnowledgeNode.code)
            .join(m.QuestionKnowledgeLink, m.QuestionKnowledgeLink.node_id == m.KnowledgeNode.id)
            .where(
                m.QuestionKnowledgeLink.question_version_id == qv.id,
                m.QuestionKnowledgeLink.review_status == "approved",
            )
        ).all()
        out.append({"year": src.exam_year, "kind": qv.kind, "knowledge": sorted(set(codes))})
    return out


@router.post("/research/runs", status_code=201)
def run_research(p: RunIn, db: Session = Depends(get_db)):
    # 整份研究报告统一时点：目标年及其后的真题不得进入回测或统计。
    rows = [r for r in _official_rows(db, p.subject) if r["year"] < p.target_year]
    stats = statistics(rows, p.target_year)
    output = {"statistics": stats, "prediction": predict(rows, p.target_year), "backtest": backtest(rows),
              "ai_inference": "BLOCKED: no authorized model interface; no AI hypothesis was generated"}
    run = m.ResearchRun(subject=p.subject, target_year=p.target_year, kind="statistics", rule_version=RULE_VERSION,
                        data_scope={"source_class": "official_exam", "years_used": stats["years_used"], "question_count": stats["question_count"], "links": "approved_only"}, output=output)
    db.add(run); db.commit()
    return {"id": run.id, "output": output, "review_status": run.review_status}


@router.get("/research/runs")
def list_runs(db: Session = Depends(get_db)):
    return [{"id": r.id, "subject": r.subject, "target_year": r.target_year, "rule_version": r.rule_version, "review_status": r.review_status, "created_at": r.created_at.isoformat()} for r in db.scalars(select(m.ResearchRun).order_by(m.ResearchRun.created_at.desc()))]


class SourceStatusIn(BaseModel):
    ingest_status: Literal["recorded", "ingested"] | None = None
    review_status: Literal["pending", "approved", "rejected"] | None = None


@router.post("/sources/{source_id}/status")
def set_source_status(source_id: str, p: SourceStatusIn, db: Session = Depends(get_db)):
    """采录状态与审核状态分别维护；仅 owner 人工操作。"""
    src = db.get(m.SourceDocument, source_id)
    if src is None:
        raise HTTPException(404, detail="source not found")
    if p.ingest_status:
        src.ingest_status = p.ingest_status
    if p.review_status:
        src.review_status = p.review_status
    db.commit()
    return {"id": src.id, "ingest_status": src.ingest_status, "review_status": src.review_status}
