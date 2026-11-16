"""学校试卷卷头识别（本地文字层 / OCR）。

R2 修正后的唯一识别模型（五项，不识别学校/学期/系列）：
- 学年度：如 2026-2027
- 年级：规范为 7/8/9/10/11/12（原卷可写“九年级”“初三”等）
- 考试类型：月考/期中/期末/统一练习；其他明确类型保留原标签
- 学科：math/chinese/english/physics/ethics
- 考试日期：单一 ``exam_date`` 字段

``exam_date`` 允许完整日期（``2026-10-12``）或原卷只写年月（``2026-10``）。没有完整日时
只保存年月，绝不补 01 日、当前日期或其他推测值。学校、学期、考试系列不在识别结果中。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date as date_type
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from typing import Any

from . import private_files as files

MAX_HEADER_TEXT_CHARS = 16_000
MAX_OCR_PAGES = 2
_IMAGE_MEDIA = {"image/png", "image/jpeg"}

_SUBJECT_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("math", ("数学",)),
    ("chinese", ("语文",)),
    ("english", ("英语",)),
    ("physics", ("物理",)),
    ("ethics", ("道德与法治", "道法", "政治")),
)

# 规范年级为数字字符串；匹配时仍兼容中文学段名称。
_GRADE_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("7", ("七年级", "初一", "7年级")),
    ("8", ("八年级", "初二", "8年级")),
    ("9", ("九年级", "初三", "9年级")),
    ("10", ("高一", "高中一年级")),
    ("11", ("高二", "高中二年级")),
    ("12", ("高三", "高中三年级")),
)

_EXAM_TYPE_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("final", ("期末考试", "期末", "学年考试")),
    ("midterm", ("期中考试", "期中")),
    ("monthly", ("月考", "月度检测", "月度考试")),
    ("unified_practice", ("统一练习",)),
)
_EXAM_TYPE_LABELS = {
    "final": "期末",
    "midterm": "期中",
    "monthly": "月考",
    "unified_practice": "统一练习",
    "other": "其他",
}

# 支持半角/全角波浪、长短横线、至；要求结束年份为起始年+1。
_ACADEMIC_YEAR_RE = re.compile(r"(20\d{2})\s*[~～—–\-至]\s*(20\d{2})\s*(?:学年度|学年|年度)?")
# 完整日期或年月；年份后必须出现年/点/斜杠/横线，避免把学年区间误识别为日期。
_DATE_RE = re.compile(
    r"(20\d{2})\s*(?:年|[./-])\s*(\d{1,2})"
    r"(?:\s*(?:月|[./-])\s*(\d{1,2})\s*日?)?"
)
# 卷头日期只在页首区域查找；试题正文中的“2020 年 6 月”等不能污染考试日期。
_DATE_HEADER_LINES = 12
_OTHER_TYPE_RE = re.compile(r"([\u4e00-\u9fa5]{2,10}(?:考试|练习|检测|测试|调研|模拟))")
_EXCLUDED_TYPE_WORDS = ("试卷", "答题卡", "数学", "语文", "英语", "物理", "化学", "历史", "地理", "生物")
_PII_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(姓名|学生姓名)\s*[:：]?\s*[^\s，,；;]{1,24}"), r"\1：[已脱敏]"),
    (re.compile(r"(学号|考号|准考证号|座位号)\s*[:：]?\s*[A-Za-z0-9-]{3,24}"), r"\1：[已脱敏]"),
    (re.compile(r"(班级)\s*[:：]?\s*[^\s，,；;]{1,20}"), r"\1：[已脱敏]"),
    (re.compile(r"\b\d{12,18}\b"), "[已脱敏编号]"),
)


@dataclass(frozen=True)
class HeaderField:
    """单个考试身份字段的识别值、来源依据与状态。"""

    status: str
    value: str | None = None
    evidence: str | None = None


@dataclass
class HeaderRecognition:
    """卷头识别结果：只有五项必填字段 + 字段级证据。"""

    subject: str | None
    academic_year: str | None
    grade: str | None
    exam_type: str | None
    exam_type_label: str | None
    exam_date: str | None
    confidence: str
    complete: bool
    fields: dict[str, HeaderField] = field(default_factory=dict)
    text_excerpt: str = ""
    text_sha256: str = ""
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["fields"] = {key: asdict(value) for key, value in self.fields.items()}
        return payload


def _field(status: str, value: str | None = None, evidence: str | None = None) -> HeaderField:
    return HeaderField(status=status, value=value, evidence=evidence)


def sanitize_header_text(text: str) -> str:
    """保留完整卷头证据，但遮罩学生姓名/学号/考号等 PII 后再保存或回传。"""
    cleaned = str(text or "")
    for pattern, replacement in _PII_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    lines = [line.rstrip() for line in cleaned.splitlines() if line.strip()]
    return "\n".join(lines)[:MAX_HEADER_TEXT_CHARS]


def _run_tool(arguments: list[str], *, timeout: int = 30) -> str:
    try:
        result = subprocess.run(arguments, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.decode("utf-8", errors="replace")


def _ocr_image(image_path: Path, output_stem: Path) -> str:
    """对完整页图做本地 OCR；返回未清洗的 OCR 文本。"""
    _run_tool(["tesseract", str(image_path), str(output_stem), "-l", "chi_sim+eng", "--psm", "3"], timeout=90)
    output = output_stem.with_suffix(".txt")
    if not output.exists():
        return ""
    return output.read_text(encoding="utf-8", errors="replace")


def extract_header_text(data: bytes, media_type: str) -> str:
    """抽取前两页完整卷头区域；PDF 有文字层时优先文字层，否则前两页本地 OCR。"""
    if not data:
        return ""
    if media_type == files.DOCX_MEDIA_TYPE:
        try:
            return files.extract_docx_text(data)[:MAX_HEADER_TEXT_CHARS]
        except Exception:
            return ""
    with TemporaryDirectory(prefix="pageboy-header-") as directory:
        root = Path(directory)
        if media_type == "application/pdf":
            pdf_path = root / "header.pdf"
            pdf_path.write_bytes(data)
            text_path = root / "header.txt"
            _run_tool(
                [
                    "pdftotext",
                    "-f",
                    "1",
                    "-l",
                    str(MAX_OCR_PAGES),
                    "-layout",
                    "-enc",
                    "UTF-8",
                    str(pdf_path),
                    str(text_path),
                ]
            )
            text = text_path.read_text(encoding="utf-8", errors="replace") if text_path.exists() else ""
            if text.strip() and not files.pdf_needs_ocr(text):
                return text[:MAX_HEADER_TEXT_CHARS]
            _run_tool(
                ["pdftoppm", "-f", "1", "-l", str(MAX_OCR_PAGES), "-r", "180", "-png", str(pdf_path), str(root / "page")],
                timeout=120,
            )
            images = sorted(root.glob("page-*.png"))
            if not images:
                return ""
            page_texts = [
                f"—— 第 {index} 页（本地 OCR）——\n{_ocr_image(image, root / f'ocr-{index}')}"
                for index, image in enumerate(images[:MAX_OCR_PAGES], 1)
            ]
            return "\n".join(part for part in page_texts if part.strip())[:MAX_HEADER_TEXT_CHARS]
        if media_type in _IMAGE_MEDIA:
            image_path = root / "header.png"
            try:
                with files.Image.open(BytesIO(data)) as image:
                    image.convert("RGB").save(image_path, format="PNG")
            except Exception:
                return ""
            return _ocr_image(image_path, root / "ocr")[:MAX_HEADER_TEXT_CHARS]
        return ""


def _find_unique(
    lines: list[str],
    patterns: tuple[tuple[str, tuple[str, ...]], ...],
) -> tuple[str | None, str | None, str]:
    matches: list[tuple[str, str]] = []
    for line in lines:
        for code, aliases in patterns:
            if any(alias in line for alias in aliases):
                matches.append((code, line))
                break
    if not matches:
        return None, None, "missing"
    unique_codes = {code for code, _ in matches}
    if len(unique_codes) > 1:
        return None, "；".join(dict.fromkeys(line for _, line in matches))[:300], "ambiguous"
    return matches[0][0], matches[0][1][:300], "found"


def _subject_from_text(lines: list[str], filename: str) -> HeaderField:
    filename_hits: list[tuple[str, str]] = []
    for code, aliases in _SUBJECT_ALIASES:
        if any(alias in filename for alias in aliases):
            filename_hits.append((code, filename))
    if len({code for code, _ in filename_hits}) == 1:
        code, evidence = filename_hits[0]
        return _field("found", code, f"文件名：{evidence[:120]}")
    if len({code for code, _ in filename_hits}) > 1:
        return _field("ambiguous", None, f"文件名同时包含多个学科：{filename[:120]}")

    matches: list[tuple[str, str]] = []
    for line in lines[:30]:
        for code, aliases in _SUBJECT_ALIASES:
            if any(alias in line for alias in aliases):
                matches.append((code, line))
                break
    unique_codes = {code for code, _ in matches}
    if len(unique_codes) == 1:
        return _field("found", matches[0][0], matches[0][1][:300])
    if len(unique_codes) > 1:
        return _field("ambiguous", None, "；".join(line for _, line in matches)[:300])
    return _field("missing")


def _academic_year_from_text(text: str) -> HeaderField:
    matches = []
    for match in _ACADEMIC_YEAR_RE.finditer(text):
        start, end = int(match.group(1)), int(match.group(2))
        if end == start + 1:
            matches.append((f"{start}-{end}", match.group(0)))
    unique = {value for value, _ in matches}
    if len(unique) == 1:
        return _field("found", matches[0][0], matches[0][1])
    if len(unique) > 1:
        return _field("ambiguous", None, "；".join(raw for _, raw in matches)[:300])
    return _field("missing")


def _exam_date_from_text(text: str) -> HeaderField:
    """单一考试日期字段：完整日期或年月；不补日，不输出月份/精度辅助字段。"""
    found: list[tuple[str, str]] = []
    for match in _DATE_RE.finditer(text):
        year = int(match.group(1))
        month = int(match.group(2))
        day_text = match.group(3)
        if not (2000 <= year <= 2100 and 1 <= month <= 12):
            continue
        if day_text is None:
            found.append((f"{year:04d}-{month:02d}", match.group(0)))
            continue
        day = int(day_text)
        try:
            date_type(year, month, day)
        except ValueError:
            continue
        found.append((f"{year:04d}-{month:02d}-{day:02d}", match.group(0)))
    full = [(value, raw) for value, raw in found if len(value) == 10]
    months = [(value, raw) for value, raw in found if len(value) == 7]
    unique_full = {value for value, _ in full}
    if len(unique_full) == 1:
        full_value = full[0][0]
        # 同一月份内同时出现“2026.10”和“2026.10.12”时，采用更精确的完整日期。
        if all(value[:7] == full_value[:7] for value, _ in months):
            return _field("found", full_value, full[0][1])
        return _field("ambiguous", None, "；".join(raw for _, raw in found)[:300])
    if len(unique_full) > 1:
        return _field("ambiguous", None, "；".join(raw for _, raw in full)[:300])
    unique_months = {value for value, _ in months}
    if len(unique_months) == 1:
        return _field("found", months[0][0], months[0][1])
    if len(unique_months) > 1:
        return _field("ambiguous", None, "；".join(raw for _, raw in months)[:300])
    return _field("missing")


def _clean_other_type_label(label: str) -> str:
    """从“学年度九年级阶段检测”之类整行中剥离年级/学年前缀，只留类型标签。"""
    cleaned = re.sub(r"^.*?(?:学年度|学年|学期)", "", label).strip()
    cleaned = re.sub(r"^(?:[七八九]年级|初[一二三]|高[一二三]|[七八九])", "", cleaned).strip(" 　-—_")
    return cleaned or label.strip()


def _exam_type_from_text(lines: list[str]) -> tuple[HeaderField, str | None]:
    code, evidence, status = _find_unique(lines, _EXAM_TYPE_ALIASES)
    if status == "found":
        return _field("found", code, evidence), _EXAM_TYPE_LABELS.get(code or "", code)
    if status == "ambiguous":
        return _field("ambiguous", None, evidence), None

    candidates: list[str] = []
    for line in lines[:30]:
        for match in _OTHER_TYPE_RE.finditer(line):
            label = _clean_other_type_label(match.group(1).strip())
            if len(label) < 2 or any(word in label for word in _EXCLUDED_TYPE_WORDS):
                continue
            if label not in candidates:
                candidates.append(label)
    if len(candidates) == 1:
        return _field("found", "other", candidates[0]), candidates[0]
    if len(candidates) > 1:
        return _field("ambiguous", None, "；".join(candidates[:3])[:300]), None
    return _field("missing"), None


def recognize_header_text(text: str, filename: str = "") -> HeaderRecognition:
    """从卷头文字识别五项身份；缺失/冲突进入人工核对，不填充日期或类型。"""
    sanitized = sanitize_header_text(text)
    # OCR 常把连接号识别为中文“一/–”，只在两个年份之间做保守归一化。
    sanitized = re.sub(r"(20\d{2})\s*[—–一]\s*(20\d{2})", r"\1-\2", sanitized)
    lines = [line for line in sanitized.splitlines() if line.strip()]
    subject = _subject_from_text(lines, filename or "")
    academic_year = _academic_year_from_text(sanitized)
    grade_code, grade_evidence, grade_status = _find_unique(lines, _GRADE_ALIASES)
    grade = _field(grade_status, grade_code, grade_evidence)
    exam_type, exam_type_label = _exam_type_from_text(lines)
    # 页首区域内的日期候选；排除以题号开头的题干行，避免正文历史日期污染。
    header_date_lines = [
        line
        for line in lines[:_DATE_HEADER_LINES]
        if not re.match(r"^\s*(?:\d{1,2}[.、]|[（(]\d{1,2}[）)]|[一二三四五六七八九十]+、)", line)
    ]
    exam_date = _exam_date_from_text("\n".join(header_date_lines))

    fields = {
        "academic_year": academic_year,
        "grade": grade,
        "exam_type": exam_type,
        "subject": subject,
        "exam_date": exam_date,
    }
    required = ("academic_year", "grade", "exam_type", "subject", "exam_date")
    missing = [name for name in required if fields[name].status != "found"]
    ambiguous = [name for name in required if fields[name].status == "ambiguous"]
    confidence = "high" if not missing and not ambiguous else ("medium" if len(missing) + len(ambiguous) <= 1 else "low")
    warnings = [f"必填字段缺失：{name}" for name in missing]
    warnings.extend(f"必填字段冲突：{name}" for name in ambiguous)

    return HeaderRecognition(
        subject=subject.value,
        academic_year=academic_year.value,
        grade=grade.value,
        exam_type=exam_type.value,
        exam_type_label=exam_type_label,
        exam_date=exam_date.value,
        confidence=confidence,
        complete=not missing and not ambiguous,
        fields=fields,
        text_excerpt=sanitized,
        text_sha256=sha256(sanitized.encode("utf-8")).hexdigest(),
        warnings=warnings,
    )


def analyze_paper_bytes(data: bytes, media_type: str, filename: str) -> HeaderRecognition:
    """从已通过真实类型校验的试卷字节生成卷头识别结果。"""
    text = extract_header_text(data, media_type)
    return recognize_header_text(text, filename)
