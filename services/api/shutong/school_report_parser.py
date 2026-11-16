"""校考分析报告册解析（纯文本核心，不直接访问数据库或网络）。

输入是 PDF OCR/文字层文本（可带 ``—— 第 N 页 ——`` 标记），输出待人工核对的
报告身份、全科/学科成绩、统计范围差异、逐题表与答题卡页范围。

安全边界：
- 不在本模块读取真实 PDF、不写文件、不访问 k12100；
- 报告中的姓名/学号/考号/班级只做遮罩，不进入解析结果；
- 识别不到或字段冲突时返回缺失/低置信，不猜分数、排名或考试日期。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import re
from typing import Any

from . import private_files as files
from . import school_report_ocr as report_ocr

REPORT_SIGNAL = "分析报告册"
_REPORT_HEADERS = ("总分成绩分析", "成绩单", "小题分析表", "答题卡")
_SUBJECTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("math", ("数学",)),
    ("chinese", ("语文",)),
    ("english", ("英语",)),
    ("physics", ("物理",)),
    ("ethics", ("道德与法治", "道法", "政治")),
)
_PAGE_MARKER = re.compile(r"——\s*第\s*(\d+)\s*页(?:（[^）]*）)?\s*——")
_ACADEMIC_YEAR = re.compile(r"(20\d{2})\s*[-—~至]\s*(20\d{2})\s*学?年?度?")
_SHORT_YEAR = re.compile(r"(?<!\d)(\d{2})\s*[-—~]\s*(\d{2})\s*学?年?度?")
_GRADE = re.compile(r"(初[一二三]|[七八九]年级|高[一二三]|1[0-2]年级)")
_TYPE = re.compile(r"(期中考试|期末考试|统一练习[一二三四五六七八九十0-9]*|月考|阶段检测|模拟考试)")
_REPORT_TIME = re.compile(r"报告时间\s*[:：]?\s*([0-9]{4}\s*年\s*[0-9]{1,2}\s*月\s*[0-9]{1,2}\s*日[^\n]*)")
_SUBJECT_HEADING = re.compile(r"([\u4e00-\u9fa5]{1,6})\s*成绩分析")
_PII_PATTERNS = (
    (re.compile(r"朝阳\s*\d+\s*班"), "[班级已脱敏]"),
    (re.compile(r"[\u4e00-\u9fa5]{2,4}(?=同学)"), "[已脱敏]"),
    (re.compile(r"[\u4e00-\u9fa5]{2,4}(?=分析报告册)"), "[已脱敏]"),
    (re.compile(r"(姓名|学生姓名)\s*[:：]?\s*[^\s，,；;]{1,24}"), "姓名：[已脱敏]"),
    (re.compile(r"(学号|考号|准考证号|座位号)\s*[:：]?\s*[A-Za-z0-9-]{3,24}"), "编号：[已脱敏]"),
    (re.compile(r"(班级)\s*[:：]?\s*[^\s，,；;]{1,24}"), "班级：[已脱敏]"),
    (re.compile(r"(同学)"), ""),
)
_QUESTION_TYPE = re.compile(r"(单选题|多选题|判断题|主观题|填空题|简答题|听力题|作文|默写)")
_DIFFICULTY = re.compile(r"(容易|一般|较易|较难|困难|中等|难)")


@dataclass
class ReportSubject:
    subject: str
    name: str
    score: float | None = None
    max_score: float | None = None
    class_rank: int | None = None
    grade_rank: int | None = None
    participants: int | None = None
    class_highest: float | None = None
    grade_highest: float | None = None
    score_rate: float | None = None
    page: int | None = None


@dataclass
class ReportQuestion:
    subject: str
    number: str
    question_type: str | None
    difficulty: str | None
    max_score: float | None
    score: float | None
    score_rate: float | None
    page: int
    confidence: str = "medium"


@dataclass
class ReportIdentity:
    title: str | None
    academic_year: str | None
    grade: str | None
    exam_type: str | None
    exam_sequence: int | None
    exam_month: str | None
    report_time: str | None
    source_sha256: str


@dataclass
class ReportDocument:
    kind: str
    confidence: str
    identity: ReportIdentity
    report_total_score: float | None = None
    report_total_max: float | None = None
    total_class_rank: int | None = None
    total_grade_rank: int | None = None
    total_participants: int | None = None
    listed_subject_score: float | None = None
    listed_subject_max: float | None = None
    scope_status: str = "NEEDS_REVIEW"
    subjects: list[ReportSubject] = field(default_factory=list)
    questions: list[ReportQuestion] = field(default_factory=list)
    answer_card_pages: dict[str, list[int]] = field(default_factory=dict)
    pages: int = 0
    warnings: list[str] = field(default_factory=list)
    text_sha256: str = ""
    text_excerpt: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def sanitize_report_text(text: str) -> str:
    cleaned = str(text or "")
    for pattern, replacement in _PII_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned.strip()


def split_pages(text: str) -> list[tuple[int, str]]:
    """按 OCR 页码标记切页；无标记时视为单页。"""
    marker_matches = list(_PAGE_MARKER.finditer(text))
    if not marker_matches:
        return [(1, text)]
    pages: list[tuple[int, str]] = []
    for index, marker in enumerate(marker_matches):
        start = marker.end()
        end = marker_matches[index + 1].start() if index + 1 < len(marker_matches) else len(text)
        pages.append((int(marker.group(1)), text[start:end]))
    return pages


def _norm_number(value: str) -> float | None:
    try:
        return float(value.replace("，", "").replace(",", "").rstrip("%"))
    except (TypeError, ValueError):
        return None


def _subject_code(name: str) -> str | None:
    for code, aliases in _SUBJECTS:
        if any(alias in name for alias in aliases):
            return code
    return None


def _grade_code(value: str | None) -> str | None:
    if not value:
        return None
    mapping = {"初一": "7", "初二": "8", "初三": "9", "七年级": "7", "八年级": "8", "九年级": "9"}
    return mapping.get(value) or (value[:2] if value[:1].isdigit() else None)


def _academic_year(text: str) -> str | None:
    match = _ACADEMIC_YEAR.search(text)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    short = _SHORT_YEAR.search(text)
    if short and int(short.group(2)) == int(short.group(1)) + 1:
        return f"20{short.group(1)}-20{short.group(2)}"
    return None


def _exam_sequence(exam_type: str | None) -> int | None:
    if not exam_type or not exam_type.startswith("统一练习"):
        return None
    suffix = exam_type.removeprefix("统一练习")
    if suffix in {"一", "1"}:
        return 1
    if suffix in {"二", "2"}:
        return 2
    if suffix in {"三", "3"}:
        return 3
    return None


def _identity(pages: list[tuple[int, str]], digest: str) -> ReportIdentity:
    first = next((text for _, text in pages if text.strip()), "")
    joined = "\n".join(text for _, text in pages[:3])
    title = next((line.strip() for line in first.splitlines() if line.strip()), None)
    report_time = _REPORT_TIME.search(first)
    year = _academic_year(joined)
    grade_match = _GRADE.search(joined)
    exam_match = _TYPE.search(first) or _TYPE.search(joined)
    exam_type = exam_match.group(1) if exam_match else None
    return ReportIdentity(
        title=title,
        academic_year=year,
        grade=_grade_code(grade_match.group(1) if grade_match else None),
        exam_type=exam_type,
        exam_sequence=_exam_sequence(exam_type),
        exam_month=None,
        report_time=report_time.group(1).strip() if report_time else None,
        source_sha256=digest,
    )


def _row_values(line: str) -> list[float]:
    cleaned = re.sub(r"朝阳\s*\d+\s*班|班级\s*[:：]?|[\u4e00-\u9fa5]{1,8}班", " ", line)
    numbers = [_norm_number(token) for token in re.findall(r"\d+(?:\.\d+)?%?", cleaned)]
    return [value for value in numbers if value is not None]


def _subject_row(line: str) -> tuple[str, list[float]] | None:
    code = _subject_code(line)
    if code is None:
        return None
    values = _row_values(line)
    return (code, values) if values else None


def _parse_totals(pages: list[tuple[int, str]]) -> tuple[dict[str, ReportSubject], dict[str, Any], list[str]]:
    subjects: dict[str, ReportSubject] = {}
    total: dict[str, Any] = {}
    warnings: list[str] = []
    for page_number, text in pages[:4]:
        lines = [line for line in text.splitlines() if line.strip()]
        header = " ".join(lines[:20])
        has_participants = "实考人数" in header or "REAR" in header
        for line in lines:
            if _subject_code(line) is None:
                values = _row_values(line)
                if len(values) >= 6 and 200 < values[0] <= 1000 and values[1] <= values[0] and not total.get("values"):
                    total = {"values": values, "page": page_number, "has_participants": has_participants}
                    continue
            if "总分" in line and _subject_code(line) is None:
                values = _row_values(line)
                if len(values) >= 2 and 200 < values[0] <= 1000 and values[1] <= values[0] and not total.get("values"):
                    total = {"values": values, "page": page_number, "has_participants": has_participants}
                continue
            row = _subject_row(line)
            if row is None:
                continue
            code, values = row
            if code in subjects:
                continue
            # 常见列：满分 得分 班排 年排 [实考人数] 班级最高 年级最高
            if len(values) < 2:
                continue
            max_score, score = values[0], values[1]
            class_rank = int(values[2]) if len(values) > 2 else None
            grade_rank = int(values[3]) if len(values) > 3 else None
            has_row_participants = has_participants or len(values) >= 7
            participants = int(values[4]) if has_row_participants and len(values) > 4 else None
            offset = 1 if has_row_participants else 0
            class_highest = values[4 + offset] if len(values) > 4 + offset else None
            grade_highest = values[5 + offset] if len(values) > 5 + offset else None
            subjects[code] = ReportSubject(
                subject=code,
                name=next(alias for c, aliases in _SUBJECTS if c == code for alias in aliases if alias in line),
                score=score,
                max_score=max_score,
                class_rank=class_rank,
                grade_rank=grade_rank,
                participants=participants,
                class_highest=class_highest,
                grade_highest=grade_highest,
                page=page_number,
            )
    total_values = total.get("values", [])
    total_data: dict[str, Any] = {"page": total.get("page")}
    if len(total_values) >= 2:
        total_data.update(
            report_total_max=total_values[0],
            report_total_score=total_values[1],
            total_class_rank=int(total_values[2]) if len(total_values) > 2 else None,
            total_grade_rank=int(total_values[3]) if len(total_values) > 3 else None,
            total_participants=int(total_values[4]) if total.get("has_participants") and len(total_values) > 4 else None,
        )
    else:
        warnings.append("未识别到总分成绩行")
    if not subjects:
        warnings.append("未识别到学科成绩行")
    return subjects, total_data, warnings


def _scope(subjects: dict[str, ReportSubject], total_data: dict[str, Any]) -> tuple[float | None, float | None, str]:
    if not subjects or total_data.get("report_total_score") is None:
        return None, None, "NEEDS_REVIEW"
    listed_score = round(sum(item.score or 0 for item in subjects.values()), 2)
    listed_max = round(sum(item.max_score or 0 for item in subjects.values()), 2)
    total_score = total_data["report_total_score"]
    total_max = total_data.get("report_total_max")
    if total_max == listed_max and abs(total_score - listed_score) < 0.01:
        return listed_score, listed_max, "CONSISTENT"
    if total_max is not None and abs(total_max - listed_max) > 0.01 and abs(total_score - listed_score) < 0.01:
        return listed_score, listed_max, "DIFFERENT_SCOPE_POSSIBLE"
    if total_max is not None and abs(total_max - listed_max) > 0.01:
        for item in subjects.values():
            if item.score is None or item.max_score is None:
                continue
            if abs(total_score - (listed_score - item.score)) < 0.01 and abs(total_max - (listed_max - item.max_score)) < 0.01:
                return listed_score, listed_max, "DIFFERENT_SCOPE_POSSIBLE"
        return listed_score, listed_max, "UNEXPLAINED"
    return listed_score, listed_max, "NEEDS_REVIEW"


def _normalize_question_type(raw: str | None) -> str | None:
    text = str(raw or "").strip()
    if not text:
        return None
    if "单" in text:
        return "单选题"
    if "主" in text:
        return "主观题"
    if "判" in text:
        return "判断题"
    if "听" in text:
        return "听力题"
    return text or None


def _normalize_difficulty(raw: str | None) -> tuple[str | None, bool]:
    """归一化 OCR 常见失真；返回 (难度, 是否经过归一化)。"""
    text = re.sub(r"^[。.s·*\-_]+", "", str(raw or "").strip()).strip()
    if not text:
        return None, False
    if "困" in text:
        return "困难", "困难" not in text
    if "难" in text:
        return "较难", text != "较难"
    if text in {"容易", "较易"}:
        return "容易", text != "容易"
    if text in {"一般", "中等"}:
        return "一般", text != "一般"
    if "一役" in text or text.upper() in {"BA", "BOE", "RA", "BS"}:
        return "一般", True
    return text, False


def _question_rows(page_number: int, text: str) -> list[ReportQuestion]:
    rows: list[ReportQuestion] = []
    for line in text.splitlines():
        type_match = _QUESTION_TYPE.search(line)
        if not type_match:
            continue
        tokens = re.findall(r"\S+", line)
        number = tokens[0].strip("：:")
        if not re.match(r"^(?:\d{1,3}(?:[（(][0-9一二三四五六七八九十]+[）)])?|默写|听力题)$", number):
            continue
        difficulty_match = _DIFFICULTY.search(line)
        numbers = [_norm_number(token) for token in re.findall(r"\d+(?:\.\d+)?%?", line)]
        values = [value for value in numbers if value is not None]
        # 题号数字也在 values 中；取题型后的满分/得分/得分率。
        number_match = re.match(r"\d+", number)
        tail = values[1:] if values and number_match and values[0] == float(number_match.group(0)) else values
        if len(tail) < 2:
            continue
        max_score, score = tail[0], tail[1]
        rate = float(tail[2]) if len(tail) > 2 and "%" in line else None
        difficulty_value, difficulty_normalized = _normalize_difficulty(difficulty_match.group(1) if difficulty_match else None)
        question_type_value = _normalize_question_type(type_match.group(1))
        rows.append(
            ReportQuestion(
                subject="",
                number=number,
                question_type=question_type_value,
                difficulty=difficulty_value,
                max_score=max_score,
                score=score,
                score_rate=rate,
                page=page_number,
            )
        )
    return rows


def _score_row_values(text: str) -> list[float]:
    lines = [line for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if line.strip() != "成绩单":
            continue
        for candidate in lines[index + 1 : index + 4]:
            values = _row_values(candidate)
            if len(values) >= 2:
                return values
    return []


def _page_subjects(pages: list[tuple[int, str]], subjects: dict[str, ReportSubject]) -> dict[int, str]:
    """按页内“学科成绩分析”标题或成绩单分数归属学科；无证据不猜。"""
    page_subject: dict[int, str] = {}
    current: str | None = None
    for page_number, text in pages:
        headings = [_subject_code(match.group(1)) for match in _SUBJECT_HEADING.finditer(text)]
        headings = [code for code in headings if code]
        if headings:
            current = headings[0]
        elif "成绩单" in text:
            values = _score_row_values(text)
            if values:
                matches = [
                    code
                    for code, item in subjects.items()
                    if item.score is not None and abs(item.score - values[0]) < 0.01
                ]
                if len(matches) == 1:
                    current = matches[0]
        if current:
            page_subject[page_number] = current
    return page_subject


def _section_score_override(pages: list[tuple[int, str]], subjects: dict[str, ReportSubject]) -> None:
    """用学科页成绩单覆盖第 2 页列错位的排名/实考人数/最高分。"""
    for page_number, text in pages:
        # 第 2 页汇总表也有“成绩单”与总分/学科行，不能让汇总表覆盖学科页排名。
        if "小题分析表" not in text:
            continue
        code = None
        headings = [_subject_code(match.group(1)) for match in _SUBJECT_HEADING.finditer(text)]
        headings = [item for item in headings if item]
        if headings:
            code = headings[0]
        if code is None and "成绩单" in text:
            values = _score_row_values(text)
            if values:
                matches = [key for key, item in subjects.items() if item.score is not None and abs(item.score - values[0]) < 0.01]
                if len(matches) == 1:
                    code = matches[0]
        if code is None or code not in subjects:
            continue
        values = _score_row_values(text)
        if len(values) < 5:
            continue
        subject = subjects[code]
        subject.score = values[0]
        subject.class_rank = int(values[1]) if len(values) > 1 else subject.class_rank
        subject.grade_rank = int(values[2]) if len(values) > 2 else subject.grade_rank
        if len(values) >= 7:
            subject.participants = int(values[3])
            subject.score_rate = values[4]
            subject.class_highest = values[5]
            subject.grade_highest = values[6]
        else:
            subject.class_highest = values[3] if len(values) > 3 else subject.class_highest
            subject.grade_highest = values[4] if len(values) > 4 else subject.grade_highest
        subject.page = page_number


def _answer_cards(pages: list[tuple[int, str]], page_subject: dict[int, str]) -> dict[str, list[int]]:
    """按结构定位答题卡页：学科逐题表之后、下一份成绩单之前、低文本密度页。

    真实报告册的答题卡页通常没有“答题卡”文字（整页表格/作答区），因此不能靠标题；
    也不能硬编码页码。总结建议页明确排除。
    """
    cards: dict[str, list[int]] = {}
    current: str | None = None
    after_question_table = False
    for page_number, text in pages:
        has_score = "成绩单" in text
        has_question = "小题分析表" in text
        subject = page_subject.get(page_number)
        if has_question and subject:
            current = subject
            after_question_table = True
            continue
        if has_score:
            current = subject or current
            after_question_table = False
            continue
        if "总结建议" in text:
            continue
        if after_question_table and current and len(text.strip()) <= 1400:
            cards.setdefault(current, []).append(page_number)
    return cards


def parse_report_text(text: str, *, filename: str = "", digest: str = "") -> ReportDocument:
    sanitized = sanitize_report_text(text)
    pages = split_pages(sanitized)
    kind, kind_confidence = classify_report_text(sanitized)
    identity = _identity(pages, digest or sha256(sanitized.encode("utf-8")).hexdigest())
    if kind != "exam_analysis_report":
        return ReportDocument(
            kind=kind,
            confidence=kind_confidence,
            identity=identity,
            pages=len(pages),
            text_sha256=sha256(sanitized.encode("utf-8")).hexdigest(),
            text_excerpt=sanitized[:2000],
        )
    subject_map, total_data, warnings = _parse_totals(pages)
    _section_score_override(pages, subject_map)
    questions: list[ReportQuestion] = []
    page_subject = _page_subjects(pages, subject_map)
    seen_questions: set[tuple[str, str]] = set()
    for page_number, page_text in pages:
        code = page_subject.get(page_number)
        if code is None or "小题分析表" not in page_text:
            continue
        for row in _question_rows(page_number, page_text):
            key = (code, row.number)
            if key in seen_questions:
                continue
            seen_questions.add(key)
            row.subject = code
            questions.append(row)
    listed_score, listed_max, scope = _scope(subject_map, total_data)
    report = ReportDocument(
        kind=kind,
        confidence=kind_confidence if kind_confidence == "high" else (
            "high" if identity.academic_year and subject_map and total_data.get("report_total_score") is not None else "medium"
        ),
        identity=identity,
        report_total_score=total_data.get("report_total_score"),
        report_total_max=total_data.get("report_total_max"),
        total_class_rank=total_data.get("total_class_rank"),
        total_grade_rank=total_data.get("total_grade_rank"),
        total_participants=total_data.get("total_participants"),
        listed_subject_score=listed_score,
        listed_subject_max=listed_max,
        scope_status=scope,
        subjects=list(subject_map.values()),
        questions=questions,
        answer_card_pages=_answer_cards(pages, page_subject),
        pages=len(pages),
        warnings=warnings,
        text_sha256=sha256(sanitized.encode("utf-8")).hexdigest(),
        text_excerpt=sanitized[:2000],
    )
    if not report.questions:
        report.warnings.append("未识别到逐题分析表")
    if report.answer_card_pages and set(report.answer_card_pages) - set(subject_map):
        report.warnings.append("答题卡学科无法与成绩学科全部对应")
    return report


def classify_report_text(text: str) -> tuple[str, str]:
    """返回 (kind, confidence)，不依赖文件名；单科试卷不得被识别为报告。"""
    body = sanitize_report_text(text)
    if REPORT_SIGNAL in body and ("总分成绩分析" in body or "成绩单" in body):
        return "exam_analysis_report", "high"
    if "总分成绩分析" in body and sum(1 for code, aliases in _SUBJECTS if any(alias in body for alias in aliases)) >= 2:
        return "exam_analysis_report", "medium"
    return "unknown", "low"


def _tsv_questions(
    doc: ReportDocument,
    pages: list[dict[str, Any]],
    page_subject: dict[int, str],
    page_bodies: dict[int, str],
) -> list[ReportQuestion]:
    """用逐词 OCR 还原的列单元格重建逐题表；无表头页回退纯文本行解析。"""
    questions: list[ReportQuestion] = []
    seen: set[tuple[str, str]] = set()
    for page in pages:
        code = page_subject.get(page["page"])
        if code is None:
            continue
        rows = report_ocr.table_rows(page, ("小题", "题型", "难度", "满分", "得分", "得分率"))
        if not rows:
            for fallback in _question_rows(page["page"], page_bodies.get(page["page"], "")):
                fallback.subject = code
                key = (code, fallback.number)
                if key not in seen:
                    seen.add(key)
                    questions.append(fallback)
            continue
        for cells in rows:
            number = str(cells.get("小题") or "").strip()
            if not number:
                continue
            question_type = _normalize_question_type(str(cells.get("题型") or ""))
            difficulty, _normalized_flag = _normalize_difficulty(str(cells.get("难度") or ""))
            max_score = _norm_number(str(cells.get("满分") or ""))
            score = _norm_number(str(cells.get("得分") or ""))
            rate_text = str(cells.get("得分率") or "")
            rate = _norm_number(rate_text.rstrip("%"))
            key = (code, number)
            if key in seen:
                continue
            seen.add(key)
            questions.append(
                ReportQuestion(
                    subject=code,
                    number=number,
                    question_type=question_type,
                    difficulty=difficulty,
                    max_score=max_score,
                    score=score,
                    score_rate=rate,
                    page=page["page"],
                    confidence="medium",
                )
            )
    return questions


def parse_report_pdf(data: bytes, *, filename: str = "", digest: str = "") -> ReportDocument:
    """仅做本地 PDF OCR/文字层解析；不访问网络。

    身份/成绩/统计口径使用整页 OCR 文本；逐题表在识别到“小题分析表”的页面上
    用逐词坐标 OCR 重建列，避免跨页表格丢行。
    """
    text, _version = files.parse_text(data, "application/pdf")
    doc = parse_report_text(text, filename=filename, digest=digest or sha256(data).hexdigest())
    question_page_numbers = [number for number, body in split_pages(text) if "小题分析表" in body]
    if question_page_numbers:
        pages, page_count = report_ocr.ocr_pdf(data)
        doc.pages = page_count
        subject_map = {item.subject: item for item in doc.subjects}
        page_subject = _page_subjects(split_pages(text), subject_map)
        wanted = {number for number in question_page_numbers}
        page_bodies = {number: body for number, body in split_pages(text)}
        questions = _tsv_questions(doc, [page for page in pages if page["page"] in wanted], page_subject, page_bodies)
        if questions:
            doc.questions = questions
        else:
            doc.warnings.append("未识别到逐题分析表")
    return doc
