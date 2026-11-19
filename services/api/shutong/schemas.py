from __future__ import annotations
from datetime import date, datetime
from typing import Annotated, Any, Literal
from pydantic import BaseModel, Field, ConfigDict, HttpUrl, StringConstraints, field_validator, model_validator

# 核心四科（课标、题库、练习与诊断）
Subject = Literal["math", "chinese", "english", "physics"]
# 学校考试归档支持额外科目（ethics：道德与法治/道法，暂不建课标知识图谱）
SchoolExamSubject = Literal["math", "chinese", "english", "physics", "ethics"]
# 校考失分题标准错因分类
SchoolErrorCategory = Literal["concept", "calculation", "reading", "method", "norm", "other"]
# 校考逐题 OCR / 同步草稿可信度标记
SchoolDraftConfidence = Literal["high", "medium", "low", "skeleton_only", "external_sync", "auto_matched", "ai_matched"]

def _normalize_exam_date_input(value: Any) -> Any:
    """考试日期输入只到月：YYYY-MM 规范为当月 1 日内部锚点；完整日期保持兼容。"""
    if isinstance(value, str):
        text = value.strip()
        if len(text) == 7 and text[4] == "-" and text[:4].isdigit() and text[5:].isdigit():
            month = int(text[5:])
            if 1 <= month <= 12:
                return date(int(text[:4]), month, 1)
    return value


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
    subject: SchoolExamSubject
    exam_date: date
    title: str = Field(min_length=1)
    earned_points: float = Field(ge=0)
    max_points: float = Field(gt=0)
    confirmed_by_user: bool = False
    # 可选考试身份元数据：用于严格匹配与卷头核对，不参与总分/能力证据计算。
    school_name: str | None = Field(default=None, max_length=160)
    grade: str | None = Field(default=None, max_length=20)
    exam_type: Literal["monthly", "midterm", "final", "unified_practice", "other"] | None = None
    exam_type_label: str | None = Field(default=None, max_length=40)
    academic_year: str | None = Field(default=None, max_length=20, pattern=r"^20\d{2}-20\d{2}$")
    term: Literal["first", "second"] | None = None
    series_title: str | None = Field(default=None, max_length=160)
    external_exam_id: str | None = Field(default=None, max_length=80)

    @field_validator("exam_date", mode="before")
    @classmethod
    def _exam_date_month_input(cls, value: Any) -> Any:
        return _normalize_exam_date_input(value)

    @model_validator(mode="after")
    def check_points(self):
        if self.earned_points > self.max_points:
            raise ValueError("earned_points exceeds max_points")
        return self


class SchoolPaperScanIn(BaseModel):
    """扫描当前环境私有收件箱；只有 CLI run 才允许自动归档精确匹配原件。"""
    apply_imports: bool = False


class SchoolPaperCollectIn(BaseModel):
    """从已匹配试卷启动单场 k12100 采集；总分始终待人工核对。"""
    use_ai: bool = True
    extract_existing_pdfs: bool = True
    upload_missing_cards: bool = True
    replace_unconfirmed_drafts: bool = True
    headless: bool = False


class SchoolPaperMatchIn(BaseModel):
    """手工选择考试候选时必须显式携带人工确认标志。"""
    exam_id: str | None = Field(default=None, max_length=64)
    confirmed_by_human: bool = False


class SchoolExamRankConfirmIn(BaseModel):
    confirmed_by_human: bool = Field(strict=True)
    @model_validator(mode="after")
    def require_confirmation(self):
        if not self.confirmed_by_human:
            raise ValueError("human confirmation required")
        return self

class SchoolExamConfirmIn(BaseModel):
    """人工补充并确认待核对学校考试总分（确认后不可改写）。"""
    confirmed_by_user: bool = Field(strict=True, description="必须为 true，表示人工已核对学校考试总分")
    earned_points: float = Field(ge=0)

    @model_validator(mode="after")
    def require_confirmation(self):
        if not self.confirmed_by_user:
            raise ValueError("human confirmation required")
        return self

class DraftKnowledgeCandidate(BaseModel):
    """系统或视觉模型给出的候选知识点及简述理由，供家长核对选择。"""
    knowledge_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=160)
    reason: str = Field(default="", max_length=300)


class SchoolExamItemIn(BaseModel):
    question_label: str = Field(min_length=1, max_length=160)
    knowledge_id: str = Field(min_length=1, max_length=100)
    earned_points: float = Field(ge=0)
    max_points: float = Field(gt=0, le=100)
    scoring_origin: Literal["manual_entry", "ocr_draft"]
    error_category: SchoolErrorCategory | None = None
    error_note: str | None = Field(default=None, max_length=500)
    draft_source_attachment_id: str | None = Field(default=None, max_length=64)
    draft_confidence: SchoolDraftConfidence | None = None
    draft_reason: str | None = Field(default=None, max_length=500)
    draft_knowledge_candidates: list[DraftKnowledgeCandidate] | None = Field(default=None, max_length=5)

    @model_validator(mode="after")
    def check_points(self):
        if self.earned_points > self.max_points:
            raise ValueError("earned_points exceeds max_points")
        if self.error_note is not None:
            self.error_note = self.error_note.strip() or None
        if self.draft_reason is not None:
            self.draft_reason = self.draft_reason.strip() or None
        if self.earned_points >= self.max_points:
            # 满分题保持无错因分类，避免无效统计噪音
            self.error_category = None
        if self.scoring_origin == "manual_entry":
            # 人工直录题不保留 OCR 草稿来源元数据
            self.draft_source_attachment_id = None
            self.draft_confidence = None
            self.draft_reason = None
            self.draft_knowledge_candidates = None
        return self

class SchoolExamItemAnalysisIn(BaseModel):
    """补充或修订校考失分小题的结构化错因与复盘备注（不改写已锁定得分）。"""
    error_category: SchoolErrorCategory | None = None
    error_note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def normalize_note(self):
        if self.error_note is not None:
            self.error_note = self.error_note.strip() or None
        return self


ReflectionStatus = Literal["not_required", "pending", "completed", "needs_revision"]


class StudentSchoolReflectionSubmitIn(BaseModel):
    """学生端提交校考失分题结构化错因分类与防敷衍复盘。"""
    error_category: SchoolErrorCategory
    stuck_point: str = Field(min_length=1, max_length=300)
    fix_strategy: str = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def strip_fields(self):
        self.stuck_point = self.stuck_point.strip()
        self.fix_strategy = self.fix_strategy.strip()
        return self


class AdminReturnReflectionIn(BaseModel):
    """管理端退回学生重写复盘的理由载荷。"""
    reason: str = Field(
        default="请进一步写明具体出错步骤与可执行的改进方法",
        min_length=2,
        max_length=200,
    )

    @model_validator(mode="after")
    def strip_reason(self):
        self.reason = self.reason.strip() or "请进一步写明具体出错步骤与可执行的改进方法"
        return self


class SchoolItemStemExtractIn(BaseModel):
    """管理端按需抽取校考失分题题干与学生作答请求。"""
    mask_student_header: bool = True
    batch_size: int = Field(default=3, ge=1, le=10)


class SchoolItemStemExtractOut(BaseModel):
    """失分题题干与学生作答抽取结果（同一题永不重复 AI 解析）。"""
    requested: int
    embedded: int
    vision: int
    not_found: int
    remaining_unextracted: int = 0
    ai_called: bool
    ai_unavailable_reason: str | None = None


class SchoolItemStemPatchIn(BaseModel):
    """管理端编辑或确认单道失分题题干与学生作答。"""
    stem_text: str | None = Field(default=None, max_length=800)
    student_answer_text: str | None = Field(default=None, max_length=400)
    confirm: bool = False

    @model_validator(mode="after")
    def normalize_texts(self):
        if self.stem_text is not None:
            self.stem_text = self.stem_text.strip() or None
        if self.student_answer_text is not None:
            self.student_answer_text = self.student_answer_text.strip() or None
        return self


class SchoolExamStemsConfirmOut(BaseModel):
    """批量确认待核对题干草稿结果。"""
    confirmed_count: int


class StudentSchoolReflectionItemOut(BaseModel):
    """面向学生端的校考失分复盘条目（严禁泄露内部 knowledge_id）。"""
    item_id: str
    exam_id: str
    subject: SchoolExamSubject
    exam_title: str
    exam_date: str
    question_label: str
    topic: str
    earned_points: float
    max_points: float
    lost_points: float
    stem_excerpt: str | None = None
    student_answer_excerpt: str | None = None
    reflection_status: ReflectionStatus
    error_category: SchoolErrorCategory | None = None
    stuck_point: str = ""
    fix_strategy: str = ""
    return_reason: str | None = None
    ai_audit_mode: str | None = None
    coach_turn_count: int = 0


class SchoolCoachStartIn(BaseModel):
    """开启校考「书童陪你想」对话可选考场情境提示。"""
    scene_hint: str | None = Field(default=None, max_length=32)


class SchoolCoachMessageIn(BaseModel):
    """学生端在「书童陪你想」中发送一条复盘思考消息。"""
    content: str = Field(min_length=1, max_length=400)

    @model_validator(mode="after")
    def strip_content(self):
        self.content = self.content.strip()
        if not self.content:
            raise ValueError("消息内容不能为空")
        return self


class SchoolCoachTurnOut(BaseModel):
    """校考书童单轮对话条目。"""
    id: str
    turn_index: int
    role: Literal["user", "assistant"]
    content: str
    model_used: str | None = None
    sanitized_guard_triggered: bool = False
    created_at: str


class SchoolCoachDraftOut(BaseModel):
    """书童基于学生对话忠实归纳的提醒卡草稿（绝不自动提交）。"""
    error_category: SchoolErrorCategory | None = None
    stuck_point: str = ""
    fix_strategy: str = ""
    ready: bool = False


class SchoolCoachSessionOut(BaseModel):
    """校考失分题「书童陪你想」对话会话状态。"""
    id: str | None = None
    item_id: str
    started: bool = False
    status: str = "inactive"
    user_turn_count: int = 0
    max_user_turns: int = 12
    can_summarize: bool = False
    draft_summary: SchoolCoachDraftOut | None = None
    turns: list[SchoolCoachTurnOut] = Field(default_factory=list)


class StudentSchoolReflectionsResponseOut(BaseModel):
    """学生端校考错题复盘列表及全科待复盘计数。"""
    items: list[StudentSchoolReflectionItemOut]
    pending_counts_by_subject: dict[str, int]
    total_pending: int

class SchoolExamItemsIn(BaseModel):
    items: list[SchoolExamItemIn] = Field(min_length=1, max_length=100)

class SchoolItemConfirmIn(BaseModel):
    """人工核对 OCR/同步草稿：可同步校准得分、满分、考点编码、错因与备注。"""
    confirmed_by_human: bool = Field(strict=True, description="必须为 true，表示人工核对 OCR 草稿分数")
    earned_points: float = Field(ge=0)
    max_points: float | None = Field(default=None, gt=0, le=100)
    knowledge_id: str | None = Field(default=None, min_length=1, max_length=100)
    error_category: SchoolErrorCategory | None = None
    error_note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_confirmation(self):
        if not self.confirmed_by_human:
            raise ValueError("human confirmation required")
        if self.max_points is not None and self.earned_points > self.max_points:
            raise ValueError("earned_points exceeds max_points")
        if self.knowledge_id is not None:
            self.knowledge_id = self.knowledge_id.strip() or None
        if self.error_note is not None:
            self.error_note = self.error_note.strip() or None
        return self


class SchoolItemConfirmBatchEntryIn(SchoolItemConfirmIn):
    """批量人工确认中的单条核对载荷。"""
    item_id: str = Field(min_length=1, max_length=64)


class SchoolItemConfirmBatchIn(BaseModel):
    """批量人工确认校考草稿列表。"""
    items: list[SchoolItemConfirmBatchEntryIn] = Field(min_length=1, max_length=100)


class SchoolExamParseDraftsIn(BaseModel):
    """触发从原卷/答题卡附件抽取 M2 逐题待核对草稿的请求。"""
    attachment_ids: list[str] = Field(min_length=1, max_length=10)
    mode: Literal["auto", "skeleton_only"] = "auto"
    mask_student_header: bool = True
    replace_unconfirmed_drafts: bool = False


class ExternalSchoolItemIn(BaseModel):
    """外部平台（如 k12100.com）抓取的逐题原始得分与错题摘要。"""
    question_label: str = Field(min_length=1, max_length=160)
    earned_points: float = Field(ge=0)
    max_points: float = Field(gt=0, le=100)
    stem_text: str | None = Field(default=None, max_length=2000)
    wrong_reason: str | None = Field(default=None, max_length=500)
    knowledge_id: str | None = Field(default=None, max_length=100)
    error_category: SchoolErrorCategory | None = None

    @model_validator(mode="after")
    def check_external_item(self):
        if self.earned_points > self.max_points:
            raise ValueError("earned_points exceeds max_points")
        self.question_label = self.question_label.strip()
        if self.stem_text is not None:
            self.stem_text = self.stem_text.strip() or None
        if self.wrong_reason is not None:
            self.wrong_reason = self.wrong_reason.strip() or None
        if self.knowledge_id is not None:
            self.knowledge_id = self.knowledge_id.strip() or None
        if self.earned_points >= self.max_points:
            self.error_category = None
        return self


class SchoolExamSyncDraftsIn(BaseModel):
    """从校考平台同步待核对逐题草稿的请求载荷。"""
    items: list[ExternalSchoolItemIn] = Field(min_length=1, max_length=100)
    source_name: str = Field(default="k12100", min_length=1, max_length=64)
    use_ai: bool = True
    replace_unconfirmed_drafts: bool = False


class SchoolExamAutoAssociateIn(BaseModel):
    """按三层混合管线为校考待核对明细补全所属知识点与 Top-3 候选考点。"""
    use_ai: bool = True
    overwrite_existing: bool = False


class SchoolExamAutoAssociateOut(BaseModel):
    """校考待核对明细自动关联结果摘要。"""
    updated: int
    tier1_matched: int
    tier2_ai: int
    tier3_inferred: int
    skipped_confirmed: int


class SchoolExamErrorOverviewOut(BaseModel):
    confirmed_item_count: int
    lost_item_count: int
    unconfirmed_draft_count: int
    earned_points: float
    max_points: float
    paper_lost_points: float | None = None
    itemized_earned_points: float
    itemized_max_points: float
    itemized_lost_points: float
    unaccounted_lost_points: float | None = None
    categorized_item_count: int
    uncategorized_item_count: int
    primary_error_category: str | None = None
    primary_knowledge_id: str | None = None
    primary_knowledge_name: str | None = None


class SchoolExamErrorCategoryOut(BaseModel):
    category: str
    item_count: int
    lost_points: float
    share_of_itemized_loss: float
    question_labels: list[str]


class SchoolExamErrorNoteOut(BaseModel):
    question_label: str
    note: str


class SchoolExamErrorKnowledgeOut(BaseModel):
    knowledge_id: str
    knowledge_name: str
    item_count: int
    lost_item_count: int
    earned_points: float
    max_points: float
    lost_points: float
    exam_observed_rate: float
    share_of_itemized_loss: float
    categories: list[str]
    question_labels: list[str]
    notes: list[SchoolExamErrorNoteOut]
    practice_status: Literal["mastered", "weak", "insufficient", "untested", "not_applicable"]
    practice_observed_rate: float | None = None
    practice_sample_size: int
    diagnosis_tag: Literal["double_weak", "exam_slip", "blind_spot", "archive_review"]


class SchoolExamErrorItemOut(BaseModel):
    id: str
    question_label: str
    knowledge_id: str
    knowledge_name: str
    earned_points: float
    max_points: float
    lost_points: float
    error_category: SchoolErrorCategory | None = None
    error_note: str | None = None


class SchoolExamRecurringHitOut(BaseModel):
    exam_id: str
    title: str
    exam_date: str
    lost_points: float
    item_count: int


class SchoolExamRecurringKnowledgeOut(BaseModel):
    knowledge_id: str
    knowledge_name: str
    exam_count: int
    total_lost_points: float
    total_item_count: int
    repeat_in_current_exam: bool
    categories: list[str]
    exams: list[SchoolExamRecurringHitOut]


class SchoolExamHistorySummaryOut(BaseModel):
    same_subject_exam_count: int
    same_subject_exams_with_items: int
    recurring_count: int


class SchoolExamErrorAnalysisOut(BaseModel):
    exam_id: str
    subject: SchoolExamSubject
    title: str
    exam_date: str
    confirmed_by_user: bool
    has_taxonomy: bool
    status: Literal["insufficient_items", "no_errors_recorded", "analyzed"]
    overview: SchoolExamErrorOverviewOut
    diagnosis_summary: str
    by_category: list[SchoolExamErrorCategoryOut]
    by_knowledge: list[SchoolExamErrorKnowledgeOut]
    lost_items: list[SchoolExamErrorItemOut]
    history_summary: SchoolExamHistorySummaryOut
    recurring_knowledge: list[SchoolExamRecurringKnowledgeOut]
    disclaimer: str

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


class AdoptedSolutionOut(BaseModel):
    """管理端已采纳的改进方案（Level 2 透出给学生端的精简对策视图）。"""

    option_id: str
    title: str
    approach_focus: str
    action_steps: list[str]
    admin_note: str | None = None
    selected_at: datetime | None = None


class WrongQuestionSummaryOut(BaseModel):
    """错题汇总卡片信息（本轮刚交卷结算时不下发参考答案，由我的书童引导启发）。"""

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
    adopted_solution: AdoptedSolutionOut | None = None
    created_at: datetime | None = None


class HistoricalWrongQuestionSummaryOut(WrongQuestionSummaryOut):
    """历史近期错题回顾卡片信息（已作答历史错题展示错答与正确答案对照）。"""

    correct_answer: str


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


class K12100SyncJobStartIn(BaseModel):
    """手动发起宿主机 k12100.com 全科采集补全任务的请求参数。"""

    exam_keyword: str | None = Field(default=None, max_length=120)
    target_exam_date: date | None = None
    series_title_prefix: str | None = Field(default=None, max_length=120)
    max_exams: int = Field(default=1, ge=1, le=3)

    @field_validator("target_exam_date", mode="before")
    @classmethod
    def _target_exam_date_month_input(cls, value: Any) -> Any:
        return _normalize_exam_date_input(value)
    confirm_total_scores: bool = False
    extract_existing_pdfs: bool = True
    upload_missing_cards: bool = True
    replace_unconfirmed_drafts: bool = True
    use_ai: bool = True
    headless: bool = True


class K12100ImportBundleIn(BaseModel):
    """向开发/生产端上传宿主机脱敏 k12100 采集包执行全科补全的请求载荷。"""

    bundle: dict[str, Any]
    exam_keyword: str | None = Field(default=None, max_length=120)
    target_exam_date: date | None = None
    series_title_prefix: str | None = Field(default=None, max_length=120)
    max_exams: int = Field(default=1, ge=1, le=3)

    @field_validator("target_exam_date", mode="before")
    @classmethod
    def _target_exam_date_month_input(cls, value: Any) -> Any:
        return _normalize_exam_date_input(value)
    confirm_total_scores: bool = False
    extract_existing_pdfs: bool = True
    upload_missing_cards: bool = True
    replace_unconfirmed_drafts: bool = True
    use_ai: bool = True


class K12100ReportJobStartIn(BaseModel):
    """启动宿主机 k12100「总分」分析报告自动下载与考试档案同步任务。"""

    max_exams: int = Field(default=3, ge=1, le=3)
    headless: bool = False


class SchoolExamReportConfirmIn(BaseModel):
    confirmed: bool = False


class SchoolExamReportPatchIn(BaseModel):
    """报告身份字段人工补录；只改报告，不自动改关联考试或成绩。"""

    title: str | None = Field(default=None, max_length=200)
    academic_year: str | None = Field(default=None, max_length=20, pattern=r"^20\d{2}-20\d{2}$")
    grade: str | None = Field(default=None, max_length=20)
    exam_type: str | None = Field(default=None, max_length=40)
    exam_sequence: int | None = Field(default=None, ge=1, le=9)
    report_time: str | None = Field(default=None, max_length=80)


class SchoolExamReportSubjectIn(BaseModel):
    """为报告补录缺失学科的统计信息（不伪造原卷）。"""

    subject: SchoolExamSubject
    score: float = Field(ge=0)
    max_score: float = Field(gt=0)
    class_rank: int | None = Field(default=None, ge=1)
    grade_rank: int | None = Field(default=None, ge=1)
    participants: int | None = Field(default=None, ge=1)
    class_highest: float | None = Field(default=None, ge=0)
    grade_highest: float | None = Field(default=None, ge=0)


CognitiveGapType = Literal[
    "concept_confusion",
    "condition_omission",
    "method_misuse",
    "reasoning_break",
    "calculation_slip",
]


class DiagnosisSolutionOptionOut(BaseModel):
    """AI 为管理员提供的单个可选解决对策。"""

    option_id: Literal["opt_1", "opt_2", "opt_3"]
    title: str
    approach_focus: str
    rationale: str
    action_steps: list[str]


class AdminErrorDiagnosisOut(BaseModel):
    """管理端 AI 错因深度分析与三套可选解决方法。"""

    id: str
    attempt_id: str
    tutor_session_id: str | None = None
    root_cause_summary: str
    cognitive_gap_type: CognitiveGapType
    evidence_from_dialogue: str
    solutions: list[DiagnosisSolutionOptionOut]
    selected_option_id: Literal["opt_1", "opt_2", "opt_3"] | None = None
    admin_note: str | None = None
    model_used: str | None = None
    created_at: datetime
    updated_at: datetime
    selected_at: datetime | None = None


class AdminWrongDiagnosticListItemOut(BaseModel):
    """管理端错题诊断工作台左侧列表项。"""

    attempt_id: str
    question_version_id: str
    subject: Subject
    stem_excerpt: str
    kind: Literal["single_choice", "short_answer", "subjective"]
    options: list[str] = Field(default_factory=list)
    correct_answer: str = ""
    student_answer: str
    earned_points: float | None = None
    max_points: float
    knowledge_codes: list[str]
    knowledge_titles: list[str]
    tutor_session_id: str | None = None
    tutor_turn_count: int = 0
    has_diagnosis: bool = False
    selected_option_id: str | None = None
    selected_solution_title: str | None = None
    cognitive_gap_type: str | None = None
    created_at: datetime


class AdminWrongDiagnosticDetailOut(BaseModel):
    """管理端错题详情：含参考答案、完整数据库引导对话回放与 AI 诊断报告。"""

    attempt_id: str
    question_version_id: str
    subject: Subject
    stem: str
    kind: Literal["single_choice", "short_answer", "subjective"]
    options: list[str]
    correct_answer: str
    student_answer: str
    earned_points: float | None = None
    max_points: float
    knowledge_codes: list[str]
    knowledge_titles: list[str]
    tutor_session_id: str | None = None
    tutor_turns: list[TutorTurnOut] = Field(default_factory=list)
    diagnosis: AdminErrorDiagnosisOut | None = None
    created_at: datetime


class AdminSelectSolutionIn(BaseModel):
    """管理员选定其中一套解决对策并附加备注。"""

    option_id: Literal["opt_1", "opt_2", "opt_3"]
    admin_note: str | None = Field(default=None, max_length=500)


class KnowledgeGameSubjectConfigOut(BaseModel):
    """单学科知识点闯关双游戏（知识合成工坊 & 迷雾科技树探险）基础管控配置。"""

    subject: Subject
    alchemy_enabled: bool = True
    expedition_enabled: bool = True
    initial_shields: Literal[1, 2, 3] = 3
    prioritize_weak: bool = True
    practice_gate: Literal["recommended", "required"] = "recommended"
    reset_epoch: int = Field(default=0, ge=0)
    updated_at: datetime | None = None


class KnowledgeGameSubjectConfigIn(BaseModel):
    """管理端更新单学科知识游戏管控参数或触发学生游戏进度重置。"""

    alchemy_enabled: bool = True
    expedition_enabled: bool = True
    initial_shields: Literal[1, 2, 3] = 3
    prioritize_weak: bool = True
    practice_gate: Literal["recommended", "required"] = "recommended"
    increment_reset_epoch: bool = False


class KnowledgeGameConfigMapOut(BaseModel):
    """四科知识点闯关双游戏配置总表。"""

    subjects: dict[Subject, KnowledgeGameSubjectConfigOut]
