"""官方课程标准来源基线与条款定位数据契约及核验逻辑。

本模块属于 ST-019-A 基础设施，用于建立四科国家课程标准来源基线、
条款精准溯源、双页码定位（PDF物理页码与书籍印刷页码）及完整性核验。
本模块遵循纯业务纯契约原则，严禁直接覆盖或修改存量 81 个历史知识点。
"""

from __future__ import annotations

from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class SubjectEnum(str, Enum):
    """四科国家课程标准学科枚举。"""
    CHINESE = "chinese"
    MATH = "math"
    ENGLISH = "english"
    PHYSICS = "physics"


class StageEnum(str, Enum):
    """课程学段枚举，初中阶段统一为 stage4（7~9年级/初中开设阶段）。"""
    STAGE1 = "stage1"
    STAGE2 = "stage2"
    STAGE3 = "stage3"
    STAGE4 = "stage4"


class SectionTypeEnum(str, Enum):
    """课程标准栏目结构类型。"""
    CONTENT_REQUIREMENT = "content_requirement"   # 内容要求
    ACADEMIC_REQUIREMENT = "academic_requirement" # 学业要求
    TEACHING_HINT = "teaching_hint"               # 教学提示


class ReviewStatusEnum(str, Enum):
    """人工审核状态。"""
    PENDING = "pending"     # 待人工审核（候选数据集导入强约束必须且只能处于此状态）
    APPROVED = "approved"   # 人工审核通过
    REJECTED = "rejected"   # 人工审核驳回


class BeijingApplicability(BaseModel):
    """北京市初中学业水平考试（中考）适用性政策元数据。"""
    policy_doc_name: str = Field(..., min_length=2, description="北京市中考改革方案正式文件名称")
    policy_doc_number: str = Field(..., min_length=2, description="政策文件发文字号")
    applicable_exam_years: List[int] = Field(..., min_length=1, description="适用考试年度列表，如 [2025, 2026]")
    subject_total_points: int = Field(..., ge=1, le=150, description="计入总分满分值")
    exam_mode: str = Field(..., min_length=2, description="考试形式说明")
    applies_2022_curriculum_standard: bool = Field(True, description="命题是否严格依据2022年版课标")
    status: str = Field("confirmed", description="政策核验状态")


class SourceStandardMetadata(BaseModel):
    """官方课程标准原始文件登记元数据。"""
    source_id: str = Field(..., pattern=r"^MOE-[0-9]{4}-[A-Z0-9_-]+$", description="官方来源唯一代码")
    subject: SubjectEnum = Field(..., description="学科代码")
    standard_name: str = Field(..., min_length=5, description="标准文件全称")
    doc_number: str = Field(..., min_length=4, description="发文字号，如 教材〔2022〕2号")
    publisher: str = Field(..., min_length=2, description="印发机构，如 中华人民共和国教育部")
    issued_date: str = Field(..., description="印发日期，格式 YYYY-MM-DD")
    published_date: str = Field(..., description="公开挂网日期，格式 YYYY-MM-DD")
    official_effective_text: str = Field(..., min_length=4, max_length=100, description="官方通知明确载明的施行要求")
    technical_effective_date: str = Field(..., description="系统检索与版本排序的技术约定基准日期")
    effective_date_note: str = Field(..., min_length=10, description="技术约定日期说明，明确区分官方学期规定与技术推算基准日")
    effective_date: str = Field(..., description="施行生效技术约定基准日（兼容字段，等同于 technical_effective_date）")
    version_tag: str = Field(..., min_length=2, description="版本标识，如 2022年5月9日修正版")
    is_errata_revision: bool = Field(False, description="是否为官方勘误修正版本")
    errata_note: Optional[str] = Field(None, description="勘误及以此为准官方说明")
    source_url: str = Field(..., description="官方附件下载直链")
    portal_url: str = Field(..., description="官方通知发布主页")
    file_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$", description="原始附件 SHA256 哈希值")
    byte_size: int = Field(..., ge=1000, description="文件总字节数")
    page_count: int = Field(..., ge=1, description="PDF 物理总页数")
    stage_scope: List[StageEnum] = Field(..., min_length=1, description="标准覆盖学段")
    beijing_applicability: BeijingApplicability = Field(..., description="北京市中考政策适用性")


class CurriculumClause(BaseModel):
    """课程标准条款定位与拆解模型。"""
    clause_id: str = Field(
        ...,
        pattern=r"^cs:[a-z]+:[a-z0-9_-]+:s[1-4]:[a-z0-9_]+:[a-z0-9_]+:[a-z0-9_]+:[a-z0-9_]+$",
        description="条款唯一引用代码"
    )
    source_id: str = Field(..., pattern=r"^MOE-[0-9]{4}-[A-Z0-9_-]+$", description="所引用的官方来源 ID")
    subject: SubjectEnum = Field(..., description="学科代码")
    stage: StageEnum = Field(..., description="学段代码")
    domain: str = Field(..., min_length=2, description="课程领域结构代码，如 num_alg")
    part_title: str = Field(..., min_length=1, description="篇章标题")
    domain_title: str = Field(..., min_length=1, description="领域分类标题")
    theme_title: str = Field(..., min_length=1, description="主题标题")
    sub_theme: str = Field(..., min_length=1, description="子主题标题")
    section_type: SectionTypeEnum = Field(..., description="栏目类型")
    clause_number: str = Field(..., min_length=1, description="条目原文序号或编号")
    pdf_page: int = Field(..., ge=1, description="PDF 物理页码")
    print_page: int = Field(..., ge=1, description="书籍印刷页码")
    raw_text: str = Field(..., min_length=5, description="课程标准官方条文原文（逐字核对，保留原件印刷排版与字符特征）")
    standardized_text: Optional[str] = Field(None, min_length=5, description="公式与符号标准化表达（等价代数转写，用于检索与机器处理）")
    collation_note: Optional[str] = Field(None, min_length=5, description="人工核对与转写说明（如原件印刷排版、上下标转写区分等）")
    is_elective: bool = Field(False, description="是否为选学/不作考试要求内容（标有*）")
    derived_requirement: str = Field(..., min_length=2, description="结构化拆解要求（派生建议，不覆盖原文）")
    review_status: ReviewStatusEnum = Field(ReviewStatusEnum.PENDING, description="审核状态")
    legacy_mappings: List[str] = Field(default_factory=list, description="只读对应的存量81考点代码草案")

    @model_validator(mode="after")
    def validate_page_and_status(self) -> CurriculumClause:
        """校验页码逻辑与审核状态边界约束。"""
        # 正文区域物理页码应当大于等于书籍印刷页码（前言和目录占用初始物理页）
        if self.pdf_page < self.print_page:
            raise ValueError(f"PDF物理页码 ({self.pdf_page}) 不能小于书籍印刷页码 ({self.print_page})")
        return self


def calculate_sha256(file_path: Path | str) -> str:
    """计算指定文件的 SHA256 十六进制哈希串。"""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def load_curriculum_sources(sources_json_path: Path | str) -> List[SourceStandardMetadata]:
    """加载并结构化校验四科官方课标来源清单。"""
    p = Path(sources_json_path)
    if not p.exists():
        raise FileNotFoundError(f"课程标准来源登记文件不存在: {p}")
    raw_data = json.loads(p.read_text(encoding="utf-8"))
    return [SourceStandardMetadata.model_validate(item) for item in raw_data]


def load_curriculum_clauses(clauses_json_path: Path | str) -> List[CurriculumClause]:
    """加载并结构化校验课程标准条款采录集合。"""
    p = Path(clauses_json_path)
    if not p.exists():
        raise FileNotFoundError(f"课程标准条款采录文件不存在: {p}")
    raw_data = json.loads(p.read_text(encoding="utf-8"))
    return [CurriculumClause.model_validate(item) for item in raw_data]


def validate_curriculum_sources(sources: List[SourceStandardMetadata]) -> None:
    """核验四科课程标准来源清单：断言四科学科集合完整性及来源 ID 唯一性。"""
    # 1. 来源 ID 唯一性断言
    seen_source_ids = set()
    for s in sources:
        if s.source_id in seen_source_ids:
            raise ValueError(f"发现重复来源 ID: {s.source_id}")
        seen_source_ids.add(s.source_id)

    # 2. 四科学科集合完整性断言
    expected_subjects = {
        SubjectEnum.CHINESE,
        SubjectEnum.MATH,
        SubjectEnum.ENGLISH,
        SubjectEnum.PHYSICS,
    }
    actual_subjects = {s.subject for s in sources}
    if actual_subjects != expected_subjects:
        missing = sorted(s.value for s in (expected_subjects - actual_subjects))
        extra = sorted(s.value for s in (actual_subjects - expected_subjects))
        error_parts = []
        if missing:
            error_parts.append(f"缺失学科 {missing}")
        if extra:
            error_parts.append(f"冗余/未知学科 {extra}")
        raise ValueError(f"课程标准来源学科集合不完整: {'; '.join(error_parts)}")


def validate_candidate_dataset(
    sources: List[SourceStandardMetadata],
    clauses: List[CurriculumClause]
) -> None:
    """严格核验候选数据集：来源完整性、条款ID唯一性、来源学科一致性，以及强约束初始状态为 pending。"""
    # 0. 课标来源四科集合完整性与来源 ID 唯一性先验强约束
    validate_curriculum_sources(sources)

    source_map = {s.source_id: s for s in sources}
    seen_clause_ids = set()

    for c in clauses:
        # 1. 条款 ID 全局唯一性
        if c.clause_id in seen_clause_ids:
            raise ValueError(f"发现重复条款 ID: {c.clause_id}")
        seen_clause_ids.add(c.clause_id)

        # 2. 来源关联存在性
        if c.source_id not in source_map:
            raise ValueError(f"条款引用了未登记的来源 ID: {c.source_id}")

        # 3. 来源与条款学科一致性
        expected_subject = source_map[c.source_id].subject
        if c.subject != expected_subject:
            raise ValueError(f"条款学科 ({c.subject}) 与其关联来源学科 ({expected_subject}) 不一致: {c.clause_id}")

        # 4. 候选数据集状态强约束：自动生成候选只能以 pending 进入候选数据集，禁止虚构为 approved/rejected
        if c.review_status != ReviewStatusEnum.PENDING:
            raise ValueError(
                f"自动生成候选只能以 pending 状态进入候选数据集，发现非法状态 '{c.review_status.value}': {c.clause_id}"
            )


def verify_source_integrity(
    metadata: SourceStandardMetadata,
    actual_file_path: Optional[Path | str] = None
) -> dict[str, Any]:
    """核验证据完整性：来源格式、哈希对齐、文件字节与页数核实。"""
    result: dict[str, Any] = {
        "source_id": metadata.source_id,
        "subject": metadata.subject.value,
        "standard_name": metadata.standard_name,
        "metadata_verified": True,
        "file_verified": False,
        "errors": []
    }

    # 1. 基础元数据完整性校验
    if not metadata.source_url.startswith("http://www.moe.gov.cn/") and not metadata.source_url.startswith("https://www.moe.gov.cn/"):
        result["errors"].append(f"来源 URL 并非教育部官方域名: {metadata.source_url}")
        result["metadata_verified"] = False

    # 2. 如果提供了本地实际下载的原件，核验其实际哈希与大小
    if actual_file_path is not None:
        fpath = Path(actual_file_path)
        if not fpath.exists():
            result["errors"].append(f"实际原件文件不存在: {fpath}")
        else:
            actual_size = fpath.stat().st_size
            if actual_size != metadata.byte_size:
                result["errors"].append(f"文件大小不匹配: 期望 {metadata.byte_size} 字节, 实际 {actual_size} 字节")
            actual_hash = calculate_sha256(fpath)
            if actual_hash != metadata.file_sha256:
                result["errors"].append(f"文件 SHA256 哈希不匹配: 期望 {metadata.file_sha256}, 实际 {actual_hash}")
            if not result["errors"]:
                result["file_verified"] = True
    else:
        result["errors"].append("未提供原件文件路径")

    return result
