from __future__ import annotations
from datetime import date, datetime
from typing import Annotated, Any, Literal
from pydantic import BaseModel, Field, ConfigDict, HttpUrl, StringConstraints, model_validator

Subject = Literal["math", "chinese", "english", "physics"]

class SourceIn(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    subject: Subject
    exam_year: int | None = Field(default=None, ge=1990, le=2100)
    source_url: str | None = None
    rights_status: Literal["unknown", "personal_use_reviewed", "licensed"] = "unknown"
    verified: bool = False
    source_class: Literal["official_exam", "aux_book", "adapted", "school", "ai", "unclassified"] = "unclassified"
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    paper_key: str | None = Field(default=None, max_length=40)

class QuestionIn(BaseModel):
    source_document_id: str
    stem: str = Field(min_length=1)
    kind: Literal["single_choice", "short_answer", "subjective"] = "single_choice"
    options: list[str] = Field(default_factory=list)
    correct_answer: str = Field(min_length=1)
    knowledge_ids: list[str] = Field(min_length=1)
    max_points: float = Field(gt=0, le=100)
    group_context: str | None = Field(default=None, max_length=20000)
    media_attachment_id: str | None = None
    @model_validator(mode="after")
    def validate_options(self):
        if self.kind == "single_choice" and len(self.options) < 2:
            raise ValueError("single_choice needs at least 2 options")
        if self.kind == "subjective" and self.options:
            raise ValueError("subjective must not carry options")
        return self

class QuestionRevisionOut(BaseModel):
    id: str
    question_id: str
    version: int = Field(ge=2)
    status: Literal["draft"]

ReviewNote = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]

class SourceReviewIn(BaseModel):
    exam_year: int = Field(strict=True, ge=1990, le=2100)
    source_url: HttpUrl
    acquired_at: date
    rights_status: Literal["unknown", "personal_use_reviewed", "licensed"]
    rights_basis: ReviewNote
    applicable: bool = Field(strict=True)
    applicability_note: ReviewNote
    reviewed_by_human: bool = Field(strict=True, description="必须为 true，表示人工核查来源与适用性")

    @model_validator(mode="after")
    def require_review(self):
        if not self.reviewed_by_human or self.source_url.scheme != "https":
            raise ValueError("human review and HTTPS source URL required")
        return self

class ImportConfirmationIn(BaseModel):
    confirmed_by_human: bool = Field(strict=True, description="必须为 true，表示人工核对结构化题目")
    questions: list[QuestionIn] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def require_confirmation(self):
        if not self.confirmed_by_human:
            raise ValueError("human confirmation required")
        return self

class AttachmentOut(BaseModel):
    id: str
    source_document_id: str
    filename: str
    media_type: Literal[
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "image/png",
        "image/jpeg",
        "audio/mpeg",
        "audio/mp4",
    ]
    sha256: str = Field(pattern="^[0-9a-f]{64}$")
    byte_size: int = Field(gt=0)
    status: Literal["uploaded", "parsed", "needs_manual_input", "confirmed"]
    extracted_text: str | None
    parser_version: str | None
    parsed_at: datetime | None
    confirmed_at: datetime | None
    created_at: datetime
    question_version_ids: list[str]

class QuestionVersionOut(BaseModel):
    """审核台只读回显：某题源下全部版本（含草稿）的内容与状态，仅 owner 授权可见。"""
    model_config = ConfigDict(from_attributes=True)
    id: str
    question_id: str
    version: int
    status: Literal["draft", "reviewed", "published"]
    reviewed_by_human: bool
    stem: str
    kind: Literal["single_choice", "short_answer", "subjective"]
    options: list[str]
    correct_answer: str
    knowledge_ids: list[str]
    max_points: float
    group_context: str | None
    media_attachment_id: str | None

class SourceReviewMetadataOut(BaseModel):
    """读取侧元数据：来源地址允许 local:// 等非 http(s) 方案（本地语料种子），写入侧仍由 SourceReviewIn 强制 HTTPS。"""
    exam_year: int
    source_url: str
    acquired_at: date
    rights_status: Literal["unknown", "personal_use_reviewed", "licensed"]
    rights_basis: str
    applicable: bool
    applicability_note: str
    reviewed_by_human: bool

class SourceReviewRecordOut(BaseModel):
    id: str
    metadata: SourceReviewMetadataOut
    reviewed_by: str
    created_at: datetime

class SourceDetailOut(BaseModel):
    id: str
    source: SourceIn
    reviews: list[SourceReviewRecordOut]
    attachments: list[AttachmentOut]

class AttemptIn(BaseModel):
    client_attempt_id: str = Field(min_length=1, max_length=128)
    exposure_id: str
    answer: str
    hints_used: bool = False

class SelfAssessmentIn(BaseModel):
    self_earned_points: float = Field(ge=0)

class SchoolExamIn(BaseModel):
    subject: Subject
    exam_date: date
    title: str = Field(min_length=1)
    earned_points: float = Field(ge=0)
    max_points: float = Field(gt=0)
    confirmed_by_user: bool = False
    @model_validator(mode="after")
    def check_points(self):
        if self.earned_points > self.max_points:
            raise ValueError("earned_points exceeds max_points")
        return self

class SchoolExamItemIn(BaseModel):
    question_label: str = Field(min_length=1, max_length=160)
    knowledge_id: str = Field(min_length=1, max_length=100)
    earned_points: float = Field(ge=0)
    max_points: float = Field(gt=0, le=100)
    scoring_origin: Literal["manual_entry", "ocr_draft"]
    @model_validator(mode="after")
    def check_points(self):
        if self.earned_points > self.max_points:
            raise ValueError("earned_points exceeds max_points")
        return self

class SchoolExamItemsIn(BaseModel):
    items: list[SchoolExamItemIn] = Field(min_length=1, max_length=100)

class SchoolItemConfirmIn(BaseModel):
    confirmed_by_human: bool = Field(strict=True, description="必须为 true，表示人工核对 OCR 草稿分数")
    earned_points: float = Field(ge=0)

    @model_validator(mode="after")
    def require_confirmation(self):
        if not self.confirmed_by_human:
            raise ValueError("human confirmation required")
        return self

class GoalIn(BaseModel):
    subject: Subject
    target_points: float = Field(ge=0)
    max_points: float = Field(gt=0)
    minutes_per_day: int = Field(ge=5, le=240)
    @model_validator(mode="after")
    def check_points(self):
        if self.target_points > self.max_points:
            raise ValueError("target_points exceeds max_points")
        return self

class Success(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    status: str


class PracticeSessionCreateIn(BaseModel):
    """创建一轮智能综合练习或阶段诊断的请求载荷。"""

    subject: Subject
    target_count: int = Field(default=5, ge=1, le=20)
    purpose: Literal["training", "evaluation"] = "training"
    focus_knowledge_code: str | None = Field(default=None, max_length=120)


class PracticeSessionItemPlanOut(BaseModel):
    """练习轮次内单个编排槽位及作答进度。"""

    seq: int
    question_version_id: str
    selection_reason: str
    focus_knowledge_codes: list[str]
    answered: bool
    attempt_id: str | None = None
    earned_points: float | None = None
    max_points: float


class PracticeQuestionPayloadOut(BaseModel):
    """学生端作答题面载荷（严禁包含参考答案）。"""

    exposure_id: str
    question_version_id: str
    purpose: str
    unseen_at_exposure: bool
    stem: str
    kind: Literal["single_choice", "short_answer", "subjective"]
    group_context: str | None = None
    media_attachment_id: str | None = None
    options: list[str]
    max_points: float
    subject: Subject
    selection_reason: str | None = None
    knowledge_titles: list[str] = Field(default_factory=list)


class PracticeSessionOut(BaseModel):
    """练习会话总览与当前待作答题目。"""

    id: str
    subject: Subject
    purpose: Literal["training", "evaluation"]
    status: Literal["active", "in_progress", "completed"]
    target_count: int
    total_items: int
    completed_count: int
    focus_knowledge_code: str | None = None
    composition_summary: dict[str, int]
    items: list[PracticeSessionItemPlanOut]
    current_item: PracticeQuestionPayloadOut | None = None


class WrongQuestionSummaryOut(BaseModel):
    """错题汇总卡片信息（不直接下发标准答案，由 AI 引导启发）。"""

    attempt_id: str
    question_version_id: str
    subject: Subject
    stem: str
    kind: Literal["single_choice", "short_answer", "subjective"]
    options: list[str]
    student_answer: str
    earned_points: float | None = None
    max_points: float
    selection_reason: str | None = None
    knowledge_codes: list[str]
    knowledge_titles: list[str]
    tutor_session_id: str | None = None
    created_at: datetime | None = None


class PracticeSessionCompleteOut(BaseModel):
    """练习交卷结算结果与本轮错题清单。"""

    session_id: str
    status: Literal["completed"]
    answered_count: int
    correct_count: int
    wrong_count: int
    subjective_count: int
    wrong_items: list[WrongQuestionSummaryOut]


class TutorMessageIn(BaseModel):
    """学生在 AI 苏格拉底引导会话中的回复。"""

    content: str = Field(min_length=1, max_length=1000)


class TutorTurnOut(BaseModel):
    """AI 错题引导单轮对话记录。"""

    id: str
    turn_index: int
    role: Literal["assistant", "user"]
    content: str
    sanitized_guard_triggered: bool
    created_at: datetime


class TutorSessionOut(BaseModel):
    """AI 错题引导会话状态与对话轮次列表。"""

    started: bool
    id: str | None = None
    attempt_id: str
    status: str | None = None
    model_name: str | None = None
    stem: str | None = None
    student_answer: str | None = None
    knowledge_titles: list[str] = Field(default_factory=list)
    turns: list[TutorTurnOut] = Field(default_factory=list)


class KnowledgeMasteryItemOut(BaseModel):
    """单个知识节点的掌握状态与统计信息。"""

    code: str
    name: str
    domain: str | None = None
    parent_code: str | None = None
    level: int
    description: str | None = None
    is_leaf: bool
    sample_size: int
    observed_rate: float | None = None
    mastery_status: Literal["mastered", "weak", "insufficient", "untested"]


class DomainRadarItemOut(BaseModel):
    """一级知识领域掌握度聚合统计（供成长状态雷达/条形展示）。"""

    domain_code: str
    domain_name: str
    total_topics: int
    tested_topics: int
    mastered_count: int
    weak_count: int
    insufficient_count: int
    untested_count: int
    observed_rate: float | None = None


class GrowthStatusOut(BaseModel):
    """学生成长状态总览：优势、薄弱、领域雷达与当前目标。"""

    subject: Subject
    model_version: str
    release_version: str | None = None
    planning_threshold: float
    summary_counts: dict[str, int]
    strengths: list[KnowledgeMasteryItemOut]
    weaknesses: list[KnowledgeMasteryItemOut]
    developing: list[KnowledgeMasteryItemOut]
    untested_highlights: list[KnowledgeMasteryItemOut]
    domain_radar: list[DomainRadarItemOut]
    recent_wrong_count: int
    current_goal: dict[str, Any] | None = None
    disclaimer: str


class KnowledgeEdgeOut(BaseModel):
    """知识图谱关系边（层级隶属或前置依赖）。"""

    source: str
    target: str
    relation: str
    edge_type: Literal["hierarchy", "prerequisite"]


class KnowledgeGraphOut(BaseModel):
    """学生端知识图谱：已发布非选学节点、关系边与掌握状态高亮。"""

    subject: Subject
    release_version: str | None = None
    model_version: str
    summary_counts: dict[str, int]
    nodes: list[KnowledgeMasteryItemOut]
    edges: list[KnowledgeEdgeOut]
