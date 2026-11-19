"""Initial persistence models, deliberately small and without premature abstractions."""
from __future__ import annotations
from datetime import date, datetime, timezone
from typing import Any
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
    __table_args__ = (
        UniqueConstraint("learner_id", "subject", "external_exam_id", name="uq_school_exam_external_identity"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    learner_id: Mapped[str] = mapped_column(String(40), default="owner")
    subject: Mapped[str] = mapped_column(String(20))
    exam_date: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(160))
    earned_points: Mapped[float] = mapped_column(Float)
    max_points: Mapped[float] = mapped_column(Float)
    confirmed_by_user: Mapped[bool] = mapped_column(Boolean)
    # 0013：考试身份元数据仅用于严格匹配与人工核对，不替换既有 title/exam_date 语义。
    school_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(20), nullable=True)
    exam_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # R2：真实卷头出现的非四类标准类型保留原标签（如“阶段检测”），不得折叠为其他类型后误配。
    exam_type_label: Mapped[str | None] = mapped_column(String(40), nullable=True)
    academic_year: Mapped[str | None] = mapped_column(String(20), nullable=True)
    term: Mapped[str | None] = mapped_column(String(20), nullable=True)
    series_title: Mapped[str | None] = mapped_column(String(160), nullable=True)
    external_exam_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_kind: Mapped[str] = mapped_column(String(24), default="manual", server_default="manual")
    class_highest: Mapped[float | None] = mapped_column(Float, nullable=True)
    grade_highest: Mapped[float | None] = mapped_column(Float, nullable=True)
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
    # 校考错误分析结构化错因分类与复盘备注（支持事后补充/修订且绝不改写已锁定得分）
    error_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 0012：OCR/视觉识别及外部平台抓取的草稿溯源元数据（仅辅助审核确认，绝不替代人工定分）
    draft_source_attachment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    draft_confidence: Mapped[str | None] = mapped_column(String(24), nullable=True)
    draft_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft_knowledge_candidates: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    # 0021：失分题题干与学生作答（逐题仅 AI 解析一次，家长确认后才对学生与书童可见）
    stem_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    student_answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    stem_state: Mapped[str | None] = mapped_column(String(24), nullable=True)
    stem_source: Mapped[str | None] = mapped_column(String(24), nullable=True)
    stem_state_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class SchoolPaperAttachment(Base):
    __tablename__ = "school_paper_attachments"
    __table_args__ = (
        UniqueConstraint("school_exam_id", "sha256", name="uq_school_paper_attachment_exam_sha"),
    )
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


class SchoolExamPaper(Base):
    """本地发现/来源适配器取得的校考试卷；原件只存环境私有 blob，API 绝不返回 storage_key。"""
    __tablename__ = "school_exam_papers"
    __table_args__ = (UniqueConstraint("learner_id", "sha256", name="uq_school_exam_paper_owner_sha"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    learner_id: Mapped[str] = mapped_column(String(40), default="owner", index=True)
    sha256: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(128))
    byte_size: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(32))
    source_kind: Mapped[str] = mapped_column(String(24), default="local_scan")
    source_name: Mapped[str] = mapped_column(String(80), default="inbox")
    source_ref: Mapped[str] = mapped_column(String(255))
    header_text: Mapped[str | None] = mapped_column(Text)
    header_fields: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    header_confidence: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), default="needs_review")
    match_state: Mapped[str | None] = mapped_column(String(24))
    match_candidates: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    school_exam_id: Mapped[str | None] = mapped_column(ForeignKey("school_exams.id"), nullable=True, index=True)
    error_code: Mapped[str | None] = mapped_column(String(64))
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class SchoolExamScanRun(Base):
    """一次本地扫描的可审计摘要；空扫描同样留痕，便于管理端展示最近扫描时间。"""
    __tablename__ = "school_exam_scan_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    learner_id: Mapped[str] = mapped_column(String(40), default="owner", index=True)
    source_kind: Mapped[str] = mapped_column(String(24), default="local_scan")
    source_label: Mapped[str] = mapped_column(String(80), default="inbox")
    status: Mapped[str] = mapped_column(String(20), default="completed")
    discovered_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    invalid_count: Mapped[int] = mapped_column(Integer, default=0)
    needs_review_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SchoolExamRankSnapshot(Base):
    """本人排名快照（append-only）。独立于逐题能力证据，相同来源内容重复导入保持幂等。"""
    __tablename__ = "school_exam_rank_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "school_exam_id",
            "subject_scope",
            "scope",
            "source_field",
            "content_hash",
            name="uq_school_exam_rank_snapshot",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    school_exam_id: Mapped[str] = mapped_column(ForeignKey("school_exams.id"), index=True)
    learner_id: Mapped[str] = mapped_column(String(40), default="owner", index=True)
    subject_scope: Mapped[str] = mapped_column(String(20), default="total")
    scope: Mapped[str] = mapped_column(String(16))
    rank_value: Mapped[int] = mapped_column(Integer)
    participant_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    percentile: Mapped[float | None] = mapped_column(Float, nullable=True)
    highest_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_name: Mapped[str] = mapped_column(String(64), default="k12100")
    source_field: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64))
    # R2：排名归属校验。只有浏览器确认来自同一本人响应的排名才进入正式快照。
    ownership_status: Mapped[str] = mapped_column(String(20), default="unverified", server_default="unverified")
    ownership_basis: Mapped[str | None] = mapped_column(String(64), nullable=True)
    review_status: Mapped[str] = mapped_column(String(20), default="pending")
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
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
    sanitized_guard_triggered: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AiErrorDiagnosis(Base):
    """管理端 AI 错因深度剖析与三选一解决对策记录（按错题作答绑定）。"""
    __tablename__ = "ai_error_diagnoses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    learner_id: Mapped[str] = mapped_column(String(40), index=True, default="owner")
    attempt_id: Mapped[str] = mapped_column(ForeignKey("answer_attempts.id"), unique=True)
    tutor_session_id: Mapped[str | None] = mapped_column(ForeignKey("ai_tutor_sessions.id"), nullable=True)
    question_version_id: Mapped[str] = mapped_column(ForeignKey("question_versions.id"))
    subject: Mapped[str] = mapped_column(String(20), index=True)
    root_cause_summary: Mapped[str] = mapped_column(Text)
    cognitive_gap_type: Mapped[str] = mapped_column(String(40))
    evidence_from_dialogue: Mapped[str] = mapped_column(Text)
    solutions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    selected_option_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SchoolExamReport(Base):
    """本地分析报告册解析结果；多学科报告，待人工核对，不直接进入能力画像。"""
    __tablename__ = "school_exam_reports"
    __table_args__ = (
        UniqueConstraint("learner_id", "sha256", name="uq_school_exam_report_owner_sha"),
        Index(
            "uq_school_exam_report_owner_ext_id",
            "learner_id",
            "external_exam_id",
            unique=True,
            sqlite_where=text("external_exam_id IS NOT NULL"),
            postgresql_where=text("external_exam_id IS NOT NULL"),
        ),
        Index(
            "uq_school_exam_report_owner_canonical_key",
            "learner_id",
            "canonical_exam_key",
            unique=True,
            sqlite_where=text("canonical_exam_key IS NOT NULL"),
            postgresql_where=text("canonical_exam_key IS NOT NULL"),
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    learner_id: Mapped[str] = mapped_column(String(40), default="owner", index=True)
    sha256: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(128))
    byte_size: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(32))
    source_ref: Mapped[str] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    academic_year: Mapped[str | None] = mapped_column(String(20), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(20), nullable=True)
    exam_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    exam_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    report_time: Mapped[str | None] = mapped_column(String(80), nullable=True)
    external_exam_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    canonical_exam_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    exam_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    report_total_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    report_total_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_class_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_grade_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_participants: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_class_highest: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_grade_highest: Mapped[float | None] = mapped_column(Float, nullable=True)
    listed_subject_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    listed_subject_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    scope_status: Mapped[str] = mapped_column(String(32), default="NEEDS_REVIEW")
    pages: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[str] = mapped_column(String(16), default="low")
    status: Mapped[str] = mapped_column(String(24), default="needs_review")
    match_state: Mapped[str] = mapped_column(String(24), default="NEEDS_REVIEW")
    linked_exam_ids: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    subjects: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    questions: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    answer_card_pages: Mapped[dict[str, list[int]] | None] = mapped_column(JSON, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    warnings: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class SchoolExamReportAttachment(Base):
    """分析报告册答题卡页私有附件；原报告 PDF 与答题卡来源页码分别保留。"""
    __tablename__ = "school_exam_report_attachments"
    __table_args__ = (
        UniqueConstraint("report_id", "subject", "page_number", name="uq_school_exam_report_card_page"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    report_id: Mapped[str] = mapped_column(ForeignKey("school_exam_reports.id"), index=True)
    learner_id: Mapped[str] = mapped_column(String(40), default="owner")
    subject: Mapped[str] = mapped_column(String(20))
    page_number: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(64), default="image/png")
    byte_size: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(32), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    rotation: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
