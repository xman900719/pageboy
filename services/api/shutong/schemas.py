from __future__ import annotations
from datetime import date, datetime
from typing import Annotated, Literal
from pydantic import BaseModel, Field, ConfigDict, HttpUrl, StringConstraints, model_validator

Subject = Literal["math", "chinese", "english", "physics"]

class SourceIn(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    subject: Subject
    exam_year: int | None = Field(default=None, ge=1990, le=2100)
    source_url: str | None = None
    rights_status: Literal["unknown", "personal_use_reviewed", "licensed"] = "unknown"
    verified: bool = False

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
    media_type: Literal["application/pdf", "image/png", "image/jpeg", "audio/mpeg", "audio/mp4"]
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

class SourceReviewRecordOut(BaseModel):
    id: str
    metadata: SourceReviewIn
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
