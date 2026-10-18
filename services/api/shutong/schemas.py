from __future__ import annotations
from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

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
    kind: Literal["single_choice", "short_answer"] = "single_choice"
    options: list[str] = Field(default_factory=list)
    correct_answer: str = Field(min_length=1)
    knowledge_ids: list[str] = Field(min_length=1)
    max_points: float = Field(gt=0, le=100)
    @model_validator(mode="after")
    def validate_options(self):
        if self.kind == "single_choice" and len(self.options) < 2:
            raise ValueError("single_choice needs at least 2 options")
        return self

class QuestionRevisionOut(BaseModel):
    id: str
    question_id: str
    version: int = Field(ge=2)
    status: Literal["draft"]

class AttemptIn(BaseModel):
    client_attempt_id: str = Field(min_length=1, max_length=128)
    exposure_id: str
    answer: str
    hints_used: bool = False

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
