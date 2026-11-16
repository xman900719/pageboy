"""学校考试身份匹配：五个核心字段 + 歧义阻断。

R2 修正后的核心字段：
``academic_year + grade + exam_type + exam_date + subject``

红线：
1. 学校、学期、考试系列不再识别，也不参与匹配；
2. 考试日期是单一字段；完整日期按日比较，只有年月时按年月比较，不补日；
3. 五个核心字段全部一致只形成候选资格；多个候选必须用平台考试 ID 或考试全称进一步确认，
   仍不能唯一确定时返回 AMBIGUOUS；
4. 日期冲突是核心冲突，禁止静默修正为另一日期。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
import re
import unicodedata
from typing import Any, Iterable

MATCH_STATES = ("EXACT_MATCH", "AMBIGUOUS", "CONFLICT", "NOT_FOUND", "NEEDS_REVIEW")
CORE_FIELDS = ("academic_year", "grade", "exam_type", "exam_date", "subject")

_SUBJECT_CN = {
    "math": "数学",
    "chinese": "语文",
    "english": "英语",
    "physics": "物理",
    "ethics": "道德与法治",
}
_SUBJECT_ALIASES = {
    "数学": "math",
    "语文": "chinese",
    "英语": "english",
    "物理": "physics",
    "道德与法治": "ethics",
    "道法": "ethics",
}
_GRADE_ALIASES = {
    "7": "7",
    "七年级": "7",
    "初一": "7",
    "7年级": "7",
    "8": "8",
    "八年级": "8",
    "初二": "8",
    "8年级": "8",
    "9": "9",
    "九年级": "9",
    "初三": "9",
    "9年级": "9",
    "10": "10",
    "高一": "10",
    "高中一年级": "10",
    "11": "11",
    "高二": "11",
    "高中二年级": "11",
    "12": "12",
    "高三": "12",
    "高中三年级": "12",
}
_EXAM_TYPE_ALIASES = {
    "月考": "monthly",
    "月度检测": "monthly",
    "月度考试": "monthly",
    "monthly": "monthly",
    "期中": "midterm",
    "期中考试": "midterm",
    "midterm": "midterm",
    "期末": "final",
    "期末考试": "final",
    "学年考试": "final",
    "final": "final",
    "统一练习": "unified_practice",
    "统一训练": "unified_practice",
    "unified_practice": "unified_practice",
}
_KNOWN_TYPES = {"monthly", "midterm", "final", "unified_practice"}
_EXAM_TYPE_LABELS = {
    "monthly": "月考",
    "midterm": "期中",
    "final": "期末",
    "unified_practice": "统一练习",
    "other": "其他",
}
_PUNCT_RE = re.compile(r"[\s·•,，。;；:：/\\|()（）\[\]【】\-—_]+")
_SERIES_SUFFIX_RE = re.compile(
    r"\s*(?:试卷|试题|答题卡|答案|扫描件|·\s*(?:语文|数学|英语|物理|道德与法治|道法))\s*$"
)
_FULL_DATE_RE = re.compile(r"(20\d{2})\s*(?:年|[./-])\s*(\d{1,2})\s*(?:月|[./-])\s*(\d{1,2})\s*日?")
_MONTH_DATE_RE = re.compile(r"(20\d{2})\s*(?:年|[./-])\s*(\d{1,2})(?!\d)\s*月?")


def normalize_identity_text(value: Any) -> str:
    """身份字段比较前的保守归一化：仅统一全半角、大小写、空白与常见标点。"""
    text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    return _PUNCT_RE.sub("", text)


def normalize_subject(value: Any) -> str | None:
    """将中文学科名或编码归一为字典键；未知学科返回 None。"""
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw in _SUBJECT_CN:
        return raw
    if raw in _SUBJECT_ALIASES:
        return _SUBJECT_ALIASES[raw]
    for label, code in _SUBJECT_ALIASES.items():
        if label in raw:
            return code
    return None


def normalize_grade(value: Any) -> str | None:
    raw = re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or "")))
    if not raw:
        return None
    if raw in _GRADE_ALIASES:
        return _GRADE_ALIASES[raw]
    for label, code in _GRADE_ALIASES.items():
        if label in raw:
            return code
    return None


def normalize_academic_year(value: Any) -> str | None:
    raw = unicodedata.normalize("NFKC", str(value or ""))
    match = re.search(r"(20\d{2})\s*[~～—–\-至]\s*(20\d{2})", raw)
    if not match:
        return None
    start, end = int(match.group(1)), int(match.group(2))
    return f"{start}-{end}" if end == start + 1 else None


def normalize_exam_date(value: Any) -> str | None:
    """单一日期值：完整日期返回 YYYY-MM-DD，仅年月返回 YYYY-MM。"""
    if isinstance(value, date):
        return value.isoformat()
    raw = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not raw:
        return None
    full = _FULL_DATE_RE.search(raw)
    if full:
        year, month, day = int(full.group(1)), int(full.group(2)), int(full.group(3))
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None
    month_only = _MONTH_DATE_RE.search(raw)
    if month_only:
        year, month = int(month_only.group(1)), int(month_only.group(2))
        if 2000 <= year <= 2100 and 1 <= month <= 12:
            return f"{year:04d}-{month:02d}"
    return None


def normalize_exam_type(value: Any, label: Any = None) -> str | None:
    """返回可用于比较的类型键；未知类型使用原始明确标签，缺失类型返回 None。"""
    raw_value = unicodedata.normalize("NFKC", str(value or "")).strip()
    raw_label = unicodedata.normalize("NFKC", str(label or "")).strip()
    for raw in (raw_value, raw_label):
        if not raw:
            continue
        if raw in _EXAM_TYPE_ALIASES:
            return _EXAM_TYPE_ALIASES[raw]
        normalized = normalize_identity_text(raw)
        if normalized in _EXAM_TYPE_ALIASES:
            return _EXAM_TYPE_ALIASES[normalized]
        if normalized in _KNOWN_TYPES:
            return normalized
        if raw_label and raw in {raw_value, raw_label}:
            return f"label:{normalized}"
    return None


def exam_type_label(identity: "ExamIdentity") -> str | None:
    if identity.exam_type_label:
        return identity.exam_type_label
    return _EXAM_TYPE_LABELS.get(identity.exam_type or "", identity.exam_type)


@dataclass(frozen=True)
class ExamIdentity:
    """参与匹配的考试身份快照（来自本地档案或平台卷头）。"""

    exam_id: str | None
    subject: str | None
    title: str | None = None
    exam_date: str | None = None
    school_name: str | None = None
    grade: str | None = None
    exam_type: str | None = None
    exam_type_label: str | None = None
    academic_year: str | None = None
    term: str | None = None
    series_title: str | None = None
    external_exam_id: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ExamIdentity":
        return cls(
            exam_id=payload.get("exam_id") or payload.get("id"),
            subject=normalize_subject(payload.get("subject")),
            title=payload.get("title"),
            exam_date=normalize_exam_date(payload.get("exam_date")),
            school_name=payload.get("school_name"),
            grade=payload.get("grade"),
            exam_type=payload.get("exam_type"),
            exam_type_label=payload.get("exam_type_label"),
            academic_year=payload.get("academic_year"),
            term=payload.get("term"),
            series_title=payload.get("series_title"),
            external_exam_id=payload.get("external_exam_id"),
        )


@dataclass(frozen=True)
class FieldComparison:
    field: str
    label: str
    expected: str | None
    actual: str | None
    state: str  # match / conflict / missing / different


@dataclass
class CandidateAssessment:
    exam_id: str
    title: str
    exam_date: str | None
    score: int
    core_match: bool
    exact: bool
    comparisons: list[FieldComparison] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["comparisons"] = [asdict(item) for item in self.comparisons]
        return payload


@dataclass
class MatchResult:
    state: str
    confidence: str
    best_exam_id: str | None
    candidates: list[CandidateAssessment]
    reasons: list[str]
    missing_fields: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "confidence": self.confidence,
            "best_exam_id": self.best_exam_id,
            "candidates": [item.as_dict() for item in self.candidates],
            "reasons": self.reasons,
            "missing_fields": self.missing_fields,
        }


_FIELD_LABELS = {
    "subject": "学科",
    "academic_year": "学年度",
    "grade": "年级",
    "exam_type": "考试类型",
    "exam_date": "考试日期",
    "title": "考试全称",
    "external_exam_id": "平台考试 ID",
}


def _expected_value(identity: ExamIdentity, field_name: str) -> str | None:
    if field_name == "subject":
        return identity.subject
    if field_name == "academic_year":
        return normalize_academic_year(identity.academic_year)
    if field_name == "grade":
        return normalize_grade(identity.grade)
    if field_name == "exam_type":
        type_key = normalize_exam_type(identity.exam_type, identity.exam_type_label)
        return f"{type_key}|{exam_type_label(identity) or ''}" if type_key else None
    if field_name == "exam_date":
        return normalize_exam_date(identity.exam_date)
    value = getattr(identity, field_name)
    return str(value).strip() if value is not None and str(value).strip() else None


def _display_type(key: str | None) -> str | None:
    if not key:
        return None
    code, _, label = key.partition("|")
    return label or _EXAM_TYPE_LABELS.get(code, code)


def _date_values_match(expected: str, actual: str) -> bool:
    """完整日对完整日按日；任一方只有年月时按年月；不补日。"""
    left = normalize_exam_date(expected)
    right = normalize_exam_date(actual)
    if left is None or right is None:
        return False
    if len(left) == 10 and len(right) == 10:
        return left == right
    return left[:7] == right[:7]


def _compare_value(field_name: str, expected: str | None, actual: str | None) -> FieldComparison:
    label = _FIELD_LABELS[field_name]
    if expected is None or actual is None:
        return FieldComparison(field_name, label, expected, actual, "missing")
    if field_name == "exam_type":
        left, right = expected.split("|", 1), actual.split("|", 1)
        matched = left[0] == right[0] and normalize_identity_text(left[1]) == normalize_identity_text(right[1])
        return FieldComparison(
            field_name,
            label,
            _display_type(expected),
            _display_type(actual),
            "match" if matched else "conflict",
        )
    if field_name == "external_exam_id":
        matched = normalize_identity_text(expected) == normalize_identity_text(actual)
    elif field_name == "title":
        matched = normalize_identity_text(_SERIES_SUFFIX_RE.sub("", expected)) == normalize_identity_text(
            _SERIES_SUFFIX_RE.sub("", actual)
        )
    elif field_name == "exam_date":
        matched = _date_values_match(expected, actual)
    else:
        matched = normalize_identity_text(expected) == normalize_identity_text(actual)
    state = "match" if matched else ("different" if field_name == "title" else "conflict")
    return FieldComparison(field_name, label, expected, actual, state)


def _assess_candidate(header: ExamIdentity, candidate: ExamIdentity) -> CandidateAssessment | None:
    if header.subject and candidate.subject and header.subject != candidate.subject:
        return None
    compared_fields = (*CORE_FIELDS, "title", "external_exam_id")
    comparisons = [
        _compare_value(name, _expected_value(header, name), _expected_value(candidate, name)) for name in compared_fields
    ]
    by_field = {item.field: item for item in comparisons}
    core = [by_field[name] for name in CORE_FIELDS]
    core_match = all(item.state == "match" for item in core)
    core_conflicts = [item.field for item in core if item.state == "conflict"]
    # 平台 ID 是硬冲突：两边都有但不同，不能视为同一考试。
    external = by_field["external_exam_id"]
    if external.state == "conflict":
        core_conflicts.append("external_exam_id")
    conflicts = core_conflicts
    missing = [item.field for item in comparisons if item.state == "missing"]
    match_count = sum(1 for item in comparisons if item.state == "match")
    exact = core_match and not conflicts
    score = match_count * 2 + (8 if external.state == "match" else 0) + (6 if core_match else 0)
    return CandidateAssessment(
        exam_id=str(candidate.exam_id or ""),
        title=str(candidate.title or ""),
        exam_date=_expected_value(candidate, "exam_date"),
        score=score,
        core_match=core_match,
        exact=exact,
        comparisons=comparisons,
        conflicts=conflicts,
        missing=missing,
    )


def _disambiguate_exact(
    header: ExamIdentity,
    exact: list[CandidateAssessment],
) -> tuple[CandidateAssessment | None, str]:
    if len(exact) == 1:
        return exact[0], "唯一候选满足五字段核心校验"
    if header.external_exam_id:
        matching_ids = [
            item
            for item in exact
            if next(
                (
                    comparison
                    for comparison in item.comparisons
                    if comparison.field == "external_exam_id" and comparison.state == "match"
                ),
                None,
            )
        ]
        if len(matching_ids) == 1:
            return matching_ids[0], "多个五字段候选中由平台考试 ID 唯一确认"
        if len(matching_ids) > 1:
            return None, "多个候选共享同一平台考试 ID，仍存在歧义"
    if header.title:
        matching_titles = [
            item
            for item in exact
            if next(
                (comparison for comparison in item.comparisons if comparison.field == "title" and comparison.state == "match"),
                None,
            )
        ]
        if len(matching_titles) == 1:
            return matching_titles[0], "多个五字段候选中由考试全称唯一确认"
    return None, "多个候选五字段一致，缺少可唯一确认的平台考试 ID 或考试全称"


def match_exam_identity(header: ExamIdentity, candidates: Iterable[ExamIdentity | dict[str, Any]]) -> MatchResult:
    """按五字段筛选，必要时用平台 ID/全称消歧；仍歧义则阻断。"""
    parsed: list[ExamIdentity] = []
    for raw in candidates:
        candidate = raw if isinstance(raw, ExamIdentity) else ExamIdentity.from_dict(raw)
        if candidate.exam_id:
            parsed.append(candidate)
        if len(parsed) >= 50:
            break

    missing_fields = [name for name in CORE_FIELDS if _expected_value(header, name) is None]
    subject_candidates = [
        candidate for candidate in parsed if not header.subject or not candidate.subject or header.subject == candidate.subject
    ]
    if not parsed or not subject_candidates:
        return MatchResult("NOT_FOUND", "none", None, [], ["k12100/本地档案中未找到同科考试候选"], missing_fields)

    assessments = [
        assessment
        for candidate in subject_candidates
        if (assessment := _assess_candidate(header, candidate)) is not None
    ]
    assessments.sort(key=lambda item: (-item.score, item.exam_date or "", item.exam_id))
    limited = assessments[:5]
    exact = [item for item in assessments if item.exact]
    if exact:
        chosen, reason = _disambiguate_exact(header, exact)
        if chosen is not None:
            return MatchResult("EXACT_MATCH", "high", chosen.exam_id, limited, [reason], missing_fields)
        return MatchResult("AMBIGUOUS", "none", None, limited, [reason], missing_fields)

    # 存在任意核心字段冲突的候选，必须优先阻断，而不是落到部分匹配。
    conflicted = [item for item in assessments if item.conflicts]
    if conflicted:
        return MatchResult(
            "CONFLICT",
            "none",
            None,
            limited,
            [f"{len(conflicted)} 个候选存在五字段核心冲突或平台 ID 冲突"],
            missing_fields,
        )
    meaningful = [item for item in assessments if item.score > 0]
    if len(meaningful) > 1:
        return MatchResult(
            "AMBIGUOUS",
            "none",
            None,
            limited,
            ["存在多个部分一致的候选，缺少完整五字段证据"],
            missing_fields,
        )
    if meaningful:
        return MatchResult(
            "NEEDS_REVIEW",
            "none",
            None,
            limited,
            ["仅部分字段一致，缺少完整五字段证据"],
            missing_fields,
        )
    return MatchResult(
        "NEEDS_REVIEW",
        "none",
        None,
        limited,
        ["存在同科档案但没有任何五字段核心证据一致"],
        missing_fields,
    )


def header_identity_from_recognition(recognized: dict[str, Any]) -> ExamIdentity:
    """把卷头识别结果转换为匹配输入；只使用单一 exam_date。"""
    return ExamIdentity(
        exam_id=None,
        subject=normalize_subject(recognized.get("subject")),
        title=None,
        exam_date=recognized.get("exam_date"),
        grade=recognized.get("grade"),
        exam_type=recognized.get("exam_type"),
        exam_type_label=recognized.get("exam_type_label"),
        academic_year=recognized.get("academic_year"),
        external_exam_id=None,
    )
