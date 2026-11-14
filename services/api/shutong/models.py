"""Initial persistence models, deliberately small and without premature abstractions."""
from __future__ import annotations
from datetime import date, datetime, timezone
from uuid import uuid4
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Float, Index, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

def uid() -> str:
    return str(uuid4())

def now() -> datetime:
    return datetime.now(timezone.utc)

class SourceDocument(Base):
    __tablename__ = "source_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    title: Mapped[str] = mapped_column(String(256))
    subject: Mapped[str] = mapped_column(String(20))
    exam_year: Mapped[int | None] = mapped_column(Integer)
    source_url: Mapped[str | None] = mapped_column(Text)
    rights_status: Mapped[str] = mapped_column(String(32), default="unknown")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    # 0006：来源类别隔离（official_exam/aux_book/adapted/school/ai/unclassified）、原件哈希、采录与审核状态分离、卷别键。
    source_class: Mapped[str] = mapped_column(String(20), default="unclassified", server_default="unclassified")
    sha256: Mapped[str | None] = mapped_column(String(64))
    ingest_status: Mapped[str] = mapped_column(String(20), default="recorded", server_default="recorded")
    review_status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    paper_key: Mapped[str | None] = mapped_column(String(40))

class Question(Base):
    __tablename__ = "questions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    source_document_id: Mapped[str] = mapped_column(ForeignKey("source_documents.id"))
    subject: Mapped[str] = mapped_column(String(20))

class QuestionVersion(Base):
    __tablename__ = "question_versions"
    __table_args__ = (UniqueConstraint("question_id", "version", name="uq_question_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    stem: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(32), default="single_choice")
    options: Mapped[list] = mapped_column(JSON, default=list)
    correct_answer: Mapped[str] = mapped_column(Text)
    knowledge_ids: Mapped[list] = mapped_column(JSON, default=list)
    max_points: Mapped[float] = mapped_column(Float, default=1.0)
    reviewed_by_human: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    # ST-007：题组/阅读共享文段按版本自包含；听力题音频引用须为同一来源的原件附件。
    group_context: Mapped[str | None] = mapped_column(Text)
    # 不带数据库级外键：source_attachments 属 0002 表，内联 FK 会使全新 PostgreSQL 库
    # 在 0001 create_all 即失败（SQLite 容忍悬空 REFERENCES，PG 在建表时校验——2026-10-22 实测）。
    # 引用合法性由全部三个创建路径的应用层校验保证（存在/同源/owner → 422 MEDIA_ATTACHMENT_INVALID）。
    media_attachment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

class Exposure(Base):
    __tablename__ = "exposures"
    __table_args__ = (Index("uq_exposure_first_unseen", "learner_id", "question_id", unique=True, sqlite_where=text("is_unseen_at_exposure"), postgresql_where=text("is_unseen_at_exposure")),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    learner_id: Mapped[str] = mapped_column(String(40), index=True, default="owner")
    # 所有写入方必须赋值：轮换计数与未见首曝去重索引均按此列分组，NULL 会静默绕过部分唯一索引。
    question_id: Mapped[str] = mapped_column(String(36), ForeignKey("questions.id"), nullable=True)
    question_version_id: Mapped[str] = mapped_column(ForeignKey("question_versions.id"))
    purpose: Mapped[str] = mapped_column(String(20))
    is_unseen_at_exposure: Mapped[bool] = mapped_column(Boolean)
    shown_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class AnswerAttempt(Base):
    __tablename__ = "answer_attempts"
    __table_args__ = (UniqueConstraint("learner_id", "client_attempt_id", name="uq_attempt_idempotency"), Index("uq_attempt_exposure", "exposure_id", unique=True))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    learner_id: Mapped[str] = mapped_column(String(40), default="owner", index=True)
    client_attempt_id: Mapped[str] = mapped_column(String(128))
    exposure_id: Mapped[str] = mapped_column(ForeignKey("exposures.id"))
    question_version_id: Mapped[str] = mapped_column(ForeignKey("question_versions.id"))
    answer: Mapped[str] = mapped_column(Text)
    earned_points: Mapped[float | None] = mapped_column(Float)
    max_points: Mapped[float] = mapped_column(Float)
    scoring_origin: Mapped[str] = mapped_column(String(32))
    hints_used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class SelfAssessment(Base):
    __tablename__ = "self_assessments"
    __table_args__ = (Index("uq_self_assessment_attempt", "attempt_id", unique=True),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("answer_attempts.id"))
    learner_id: Mapped[str] = mapped_column(String(40), index=True, default="owner")
    # 主观自评为独立来源记录（INV-04）：一次自评不可更新，且不进客观证据（get_evidence/profile）。
    self_earned_points: Mapped[float] = mapped_column(Float)
    max_points: Mapped[float] = mapped_column(Float)
    scoring_origin: Mapped[str] = mapped_column(String(32), default="self_assessment")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class SchoolExam(Base):
    __tablename__ = "school_exams"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    learner_id: Mapped[str] = mapped_column(String(40), default="owner")
    subject: Mapped[str] = mapped_column(String(20))
    exam_date: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(160))
    earned_points: Mapped[float] = mapped_column(Float)
    max_points: Mapped[float] = mapped_column(Float)
    confirmed_by_user: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Goal(Base):
    __tablename__ = "goals"
    __table_args__ = (UniqueConstraint("learner_id", "subject", "version", name="uq_goal_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    learner_id: Mapped[str] = mapped_column(String(40), default="owner")
    subject: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(Integer)
    target_points: Mapped[float] = mapped_column(Float)
    max_points: Mapped[float] = mapped_column(Float)
    minutes_per_day: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class SourceReview(Base):
    __tablename__ = "source_reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    source_document_id: Mapped[str] = mapped_column(ForeignKey("source_documents.id"), index=True)
    exam_year: Mapped[int] = mapped_column(Integer)
    source_url: Mapped[str] = mapped_column(Text)
    acquired_at: Mapped[date] = mapped_column(Date)
    rights_status: Mapped[str] = mapped_column(String(32))
    rights_basis: Mapped[str] = mapped_column(Text)
    applicable: Mapped[bool] = mapped_column(Boolean)
    applicability_note: Mapped[str] = mapped_column(Text)
    reviewed_by: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class SourceAttachment(Base):
    __tablename__ = "source_attachments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    source_document_id: Mapped[str] = mapped_column(ForeignKey("source_documents.id"), index=True)
    owner_id: Mapped[str] = mapped_column(String(40))
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(128))
    sha256: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(32), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="uploaded")
    extracted_text: Mapped[str | None] = mapped_column(Text)
    parser_version: Mapped[str | None] = mapped_column(String(256))
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_by: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class ImportedQuestion(Base):
    __tablename__ = "imported_questions"
    question_version_id: Mapped[str] = mapped_column(ForeignKey("question_versions.id"), primary_key=True)
    attachment_id: Mapped[str] = mapped_column(ForeignKey("source_attachments.id"), index=True)

class SchoolExamItem(Base):
    __tablename__ = "school_exam_items"
    __table_args__ = (UniqueConstraint("school_exam_id", "question_label", name="uq_school_exam_item_label"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    school_exam_id: Mapped[str] = mapped_column(ForeignKey("school_exams.id"), index=True)
    question_label: Mapped[str] = mapped_column(String(160))
    knowledge_id: Mapped[str] = mapped_column(String(100))
    earned_points: Mapped[float] = mapped_column(Float)
    max_points: Mapped[float] = mapped_column(Float)
    # 原始来源，确认后不改（INV-04）："manual_entry" 录入即人工确认；"ocr_draft" 须人工确认。
    scoring_origin: Mapped[str] = mapped_column(String(32))
    confirmed_by_user: Mapped[bool] = mapped_column(Boolean)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class SchoolPaperAttachment(Base):
    __tablename__ = "school_paper_attachments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    school_exam_id: Mapped[str] = mapped_column(ForeignKey("school_exams.id"), index=True)
    owner_id: Mapped[str] = mapped_column(String(40))
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(128))
    sha256: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column(Integer)
    # 仅私有存储定位；绝不进入 HTTP 响应（AC-SEC-01）。
    storage_key: Mapped[str] = mapped_column(String(32), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Erratum(Base):
    """勘误记录：只追加，不修改原始题目内容（S1 原始内容不可变）。"""
    __tablename__ = "errata"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    question_version_id: Mapped[str] = mapped_column(ForeignKey("question_versions.id"), index=True)
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class QuestionSourceRegion(Base):
    """题目到原件页码/区域的对应关系。"""
    __tablename__ = "question_source_regions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    question_version_id: Mapped[str] = mapped_column(ForeignKey("question_versions.id"), index=True)
    page: Mapped[int] = mapped_column(Integer)
    bbox: Mapped[list | None] = mapped_column(JSON)

class KnowledgeNode(Base):
    """知识点稳定身份；名称/描述等随版本变化，节点 id 永不改变。"""
    __tablename__ = "knowledge_nodes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    subject: Mapped[str] = mapped_column(String(20))
    code: Mapped[str] = mapped_column(String(80), unique=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_nodes.id"))
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/deprecated/merged/split
    merged_into_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_nodes.id"))
    # 课标选学标记（*号内容不作中考考试要求，运行期练习与图谱需过滤隔离）
    is_elective: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class KnowledgeNodeVersion(Base):
    __tablename__ = "knowledge_node_versions"
    __table_args__ = (UniqueConstraint("node_id", "version", name="uq_knowledge_node_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    node_id: Mapped[str] = mapped_column(ForeignKey("knowledge_nodes.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    parent_node_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_nodes.id"), nullable=True)  # 版本快照历史父节点ID
    parent_code: Mapped[str | None] = mapped_column(String(80), nullable=True)  # 版本快照历史父节点编码
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(20), default="manual")  # manual/ai_suggested
    review_status: Mapped[str] = mapped_column(String(20), default="pending")
    source_clause_ids: Mapped[list | None] = mapped_column(JSON)  # 课标溯源条款ID列表
    reviewer_id: Mapped[str | None] = mapped_column(String(40))  # 真实人工审核者ID
    review_opinion: Mapped[str | None] = mapped_column(Text)  # 审核意见与依据
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 审核时间
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class KnowledgeTaxonomyRelease(Base):
    """知识库版本发布快照：记录不可变发布全貌，未审核完成前禁止发布。"""
    __tablename__ = "knowledge_taxonomy_releases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    subject: Mapped[str] = mapped_column(String(20))
    release_version: Mapped[str] = mapped_column(String(40), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft/published/archived
    snapshot: Mapped[dict] = mapped_column(JSON)
    published_by: Mapped[str | None] = mapped_column(String(40))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class QuestionKnowledgeLink(Base):
    """题目（可到小问）与知识点多对多关联；记录当时的知识点版本，历史不被覆盖。"""
    __tablename__ = "question_knowledge_links"
    __table_args__ = (UniqueConstraint("question_version_id", "sub_index", "node_id", name="uq_question_knowledge_link"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    question_version_id: Mapped[str] = mapped_column(ForeignKey("question_versions.id"), index=True)
    sub_index: Mapped[int] = mapped_column(Integer, default=0)  # 0 表示整题
    node_id: Mapped[str] = mapped_column(ForeignKey("knowledge_nodes.id"), index=True)
    node_version: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(10), default="core")  # core/aux
    evidence: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class ResearchRun(Base):
    """命题研究运行记录：区分统计分析与（未执行的）模型推理。"""
    __tablename__ = "research_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    subject: Mapped[str] = mapped_column(String(20))
    target_year: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))  # statistics/backtest
    rule_version: Mapped[str] = mapped_column(String(40))
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    model_used: Mapped[str | None] = mapped_column(String(80))
    data_scope: Mapped[dict] = mapped_column(JSON)
    output: Mapped[dict] = mapped_column(JSON)
    review_status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PracticeSession(Base):
    """综合编制练习回合：按能力缺失、知识图谱与题库编排的有限题数会话。"""
    __tablename__ = "practice_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    learner_id: Mapped[str] = mapped_column(String(40), index=True, default="owner")
    subject: Mapped[str] = mapped_column(String(20))
    purpose: Mapped[str] = mapped_column(String(20), default="training")  # training / evaluation
    target_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active / completed
    composition_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PracticeSessionItem(Base):
    """练习回合内的题目槽位与入选依据。"""
    __tablename__ = "practice_session_items"
    __table_args__ = (UniqueConstraint("session_id", "seq", name="uq_practice_session_seq"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    session_id: Mapped[str] = mapped_column(ForeignKey("practice_sessions.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"))
    question_version_id: Mapped[str] = mapped_column(ForeignKey("question_versions.id"))
    exposure_id: Mapped[str | None] = mapped_column(ForeignKey("exposures.id"), nullable=True)
    target_knowledge_codes: Mapped[list] = mapped_column(JSON, default=list)
    selection_reason: Mapped[str] = mapped_column(String(200))


class AiTutorSession(Base):
    """错题 AI 引导式讲解会话（按单次作答 attempt 绑定）。"""
    __tablename__ = "ai_tutor_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    learner_id: Mapped[str] = mapped_column(String(40), index=True, default="owner")
    attempt_id: Mapped[str] = mapped_column(ForeignKey("answer_attempts.id"), unique=True)
    question_version_id: Mapped[str] = mapped_column(ForeignKey("question_versions.id"))
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AiTutorTurn(Base):
    """AI 引导式讲解多轮对话记录。"""
    __tablename__ = "ai_tutor_turns"
    __table_args__ = (UniqueConstraint("tutor_session_id", "turn_index", name="uq_tutor_session_turn"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tutor_session_id: Mapped[str] = mapped_column(ForeignKey("ai_tutor_sessions.id"), index=True)
    turn_index: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(20))  # user / assistant
    content: Mapped[str] = mapped_column(Text)
    model_used: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
