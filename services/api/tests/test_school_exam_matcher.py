"""R2 修正版：五项卷头（含单一 exam_date）与五字段严格匹配测试。"""

from __future__ import annotations

from io import BytesIO
import shutil
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image, ImageDraw, ImageFont
import pytest

from shutong.school_exam_headers import analyze_paper_bytes, recognize_header_text, sanitize_header_text
from shutong.school_exam_matcher import ExamIdentity, match_exam_identity, normalize_exam_date

REAL_HEADER_TEXT = """2026～2027 学年度九年级统一练习
道德与法治
2026.10
"""


def _identity(**overrides) -> ExamIdentity:
    values = {
        "exam_id": "exam-a",
        "subject": "ethics",
        "title": "2026-2027 学年度九年级统一练习 · 道德与法治",
        "exam_date": "2026-10-15",
        "school_name": None,
        "grade": "9",
        "exam_type": "unified_practice",
        "exam_type_label": "统一练习",
        "academic_year": "2026-2027",
        "term": None,
        "series_title": None,
        "external_exam_id": None,
    }
    values.update(overrides)
    return ExamIdentity(**values)


def test_real_header_five_fields_and_single_exam_date():
    result = recognize_header_text(REAL_HEADER_TEXT, "九年级道德与法治统一练习.pdf")
    assert result.subject == "ethics"
    assert result.academic_year == "2026-2027"
    assert result.grade == "9"
    assert result.exam_type == "unified_practice"
    assert result.exam_type_label == "统一练习"
    assert result.exam_date == "2026-10"
    assert result.complete is True
    assert set(result.fields) == {"academic_year", "grade", "exam_type", "subject", "exam_date"}
    payload = result.as_dict()
    assert "school_name" not in payload
    assert "term" not in payload
    assert "series_title" not in payload
    assert "exam_month" not in payload
    assert "date_precision" not in payload
    assert result.text_sha256


def test_unified_practice_is_not_normalized_to_monthly_or_midterm():
    result = recognize_header_text(REAL_HEADER_TEXT, "道德与法治.pdf")
    assert result.exam_type == "unified_practice"
    assert result.exam_type_label == "统一练习"
    assert result.exam_type not in {"monthly", "midterm"}


def test_midterm_and_unified_practice_are_distinguished():
    unified = recognize_header_text(REAL_HEADER_TEXT, "道德与法治.pdf")
    midterm = recognize_header_text(
        "2026-2027学年度九年级期中考试\n道德与法治\n2026.11",
        "道德与法治.pdf",
    )
    assert unified.exam_type == "unified_practice"
    assert midterm.exam_type == "midterm"
    assert unified.exam_date != midterm.exam_date


def test_other_explicit_exam_type_keeps_original_label():
    result = recognize_header_text(
        "2026-2027学年度九年级阶段检测\n物理\n2026.12",
        "九年级物理阶段检测.pdf",
    )
    assert result.exam_type == "other"
    assert result.exam_type_label == "阶段检测"
    assert result.complete is True


def test_year_month_date_is_kept_without_fabricating_day():
    result = recognize_header_text(
        "2026-2027学年度九年级统一练习\n数学\n2026.10",
        "九年级数学统一练习.pdf",
    )
    assert result.exam_date == "2026-10"
    assert "2026-10-01" not in result.text_excerpt
    assert "date_precision" not in result.as_dict()


def test_full_date_is_preserved_as_single_field():
    result = recognize_header_text(
        "2026-2027学年度九年级统一练习\n数学\n2026年10月12日",
        "九年级数学统一练习.pdf",
    )
    assert result.exam_date == "2026-10-12"


def test_full_date_wins_over_same_month_short_date():
    result = recognize_header_text(
        "2026-2027学年度九年级统一练习 2026.10\n数学\n2026年10月12日",
        "九年级数学统一练习.pdf",
    )
    assert result.exam_date == "2026-10-12"


def test_missing_and_conflicting_required_fields_require_review():
    missing = recognize_header_text("统一练习\n道德与法治", "道德与法治.docx")
    assert missing.complete is False
    assert missing.grade is None
    assert missing.academic_year is None
    assert missing.exam_date is None
    assert "必填字段缺失：grade" in missing.warnings

    conflict = recognize_header_text(
        "2026-2027学年度九年级统一练习\n道德与法治\n2026.10\n2026.11",
        "道德与法治.docx",
    )
    assert conflict.complete is False
    assert conflict.exam_date is None
    assert "必填字段冲突：exam_date" in conflict.warnings


def test_school_term_and_series_are_not_recognized():
    result = recognize_header_text(
        "2026-2027学年度第一学期 虚构测试数据实验学校 九年级统一练习\n道德与法治\n2026.10",
        "道德与法治.pdf",
    )
    assert result.complete is True
    assert set(result.fields) == {"academic_year", "grade", "exam_type", "subject", "exam_date"}
    assert "学校" not in result.as_dict()
    assert "学期" not in result.as_dict()
    assert "系列" not in result.as_dict()


def test_pii_is_redacted_but_complete_ocr_and_evidence_are_preserved():
    raw = REAL_HEADER_TEXT + "\n姓名：张三 学号：20250101 考号：110101"
    cleaned = sanitize_header_text(raw)
    assert "张三" not in cleaned
    assert "20250101" not in cleaned
    assert "110101" not in cleaned
    assert "道德与法治" in cleaned
    assert "2026.10" in cleaned


def test_docx_header_text_extraction():
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
        + "".join(f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in REAL_HEADER_TEXT.splitlines())
        + "</w:body></w:document>"
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", document)
    recognized = analyze_paper_bytes(
        buffer.getvalue(),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "九年级道德与法治统一练习.docx",
    )
    assert recognized.complete is True
    assert recognized.exam_date == "2026-10"


_FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
_OCR_READY = bool(shutil.which("tesseract")) and bool(shutil.which("pdftoppm")) and __import__("pathlib").Path(_FONT).is_file()


@pytest.mark.skipif(not _OCR_READY, reason="本地缺少 tesseract 中文 OCR 或 CJK 字体")
def test_real_layout_scan_bottom_right_date_and_handwriting_noise():
    """真实版式回归：标题/年级同排、学科下方、右下方小字日期、手写干扰。"""
    image = Image.new("RGB", (1500, 1100), "white")
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.truetype(_FONT, 46)
    subject_font = ImageFont.truetype(_FONT, 42)
    date_font = ImageFont.truetype(_FONT, 24)
    draw.text((80, 70), "2026～2027 学年度九年级统一练习", font=title_font, fill="black")
    draw.text((82, 155), "道德与法治", font=subject_font, fill="black")
    draw.line((1190, 130, 1390, 190), fill="#3157a4", width=4)
    draw.line((1200, 250, 1360, 210), fill="#9d2f2f", width=3)
    draw.arc((1160, 90, 1420, 300), 20, 330, fill="#3157a4", width=2)
    draw.text((1240, 360), "2026.10", font=date_font, fill="#111111")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    recognized = analyze_paper_bytes(buffer.getvalue(), "image/png", "九年级道德与法治统一练习.png")
    assert recognized.academic_year == "2026-2027"
    assert recognized.grade == "9"
    assert recognized.subject == "ethics"
    assert recognized.exam_type == "unified_practice"
    assert recognized.exam_date == "2026-10"
    assert recognized.complete is True


def test_normalize_exam_date_full_and_month_only():
    assert normalize_exam_date("2026-10-12") == "2026-10-12"
    assert normalize_exam_date("2026年10月12日") == "2026-10-12"
    assert normalize_exam_date("2026.10") == "2026-10"
    assert normalize_exam_date("2026年10月") == "2026-10"
    assert normalize_exam_date("2026.02.30") is None


def test_exact_match_requires_five_core_fields_and_does_not_require_school_term_series():
    result = match_exam_identity(_identity(), [_identity()])
    assert result.state == "EXACT_MATCH"
    assert result.best_exam_id == "exam-a"


def test_month_only_header_matches_dated_candidate_in_same_month():
    header = _identity(exam_date="2026-10")
    result = match_exam_identity(header, [_identity(exam_date="2026-10-15")])
    assert result.state == "EXACT_MATCH"


def test_full_date_difference_is_conflict():
    header = _identity(exam_date="2026-10-12")
    result = match_exam_identity(header, [_identity(exam_date="2026-10-15")])
    assert result.state == "CONFLICT"


def test_same_month_multiple_unified_practice_is_ambiguous():
    result = match_exam_identity(
        _identity(exam_date="2026-10", title=None),
        [
            _identity(exam_id="exam-a", title="九年级统一练习 A", exam_date="2026-10-15"),
            _identity(exam_id="exam-b", title="九年级统一练习 B", exam_date="2026-10-20"),
        ],
    )
    assert result.state == "AMBIGUOUS"
    assert result.best_exam_id is None
    assert len(result.candidates) == 2


def test_platform_exam_id_disambiguates_multiple_five_field_candidates():
    result = match_exam_identity(
        _identity(exam_date="2026-10", title=None, external_exam_id="platform-001"),
        [
            _identity(exam_id="exam-a", title="A", exam_date="2026-10-15", external_exam_id="platform-001"),
            _identity(exam_id="exam-b", title="B", exam_date="2026-10-20", external_exam_id="platform-002"),
        ],
    )
    assert result.state == "EXACT_MATCH"
    assert result.best_exam_id == "exam-a"


def test_exam_full_title_disambiguates_when_no_platform_id():
    result = match_exam_identity(
        _identity(exam_date="2026-10", title="2026-2027 学年度九年级统一练习 · 道德与法治"),
        [
            _identity(exam_id="exam-a", title="2026-2027 学年度九年级统一练习 · 道德与法治", exam_date="2026-10-15"),
            _identity(exam_id="exam-b", title="2026-2027 学年度九年级统一练习 · 道德与法治（备用）", exam_date="2026-10-20"),
        ],
    )
    assert result.state == "EXACT_MATCH"
    assert result.best_exam_id == "exam-a"


def test_same_month_different_exam_type_is_conflict():
    result = match_exam_identity(
        _identity(exam_date="2026-10"),
        [_identity(exam_id="exam-b", exam_date="2026-10-15", exam_type="midterm", exam_type_label="期中")],
    )
    assert result.state == "CONFLICT"
    assert result.best_exam_id is None


def test_date_mismatch_is_conflict_not_silent_correction():
    result = match_exam_identity(
        _identity(exam_date="2026-11", title=None),
        [_identity(exam_date="2026-10-15")],
    )
    assert result.state == "CONFLICT"
    assert all(candidate.exact is False for candidate in result.candidates)


def test_exam_day_inside_month_is_not_required_for_month_only_header():
    result = match_exam_identity(
        _identity(exam_date="2026-10"),
        [
            _identity(exam_id="exam-a", exam_date="2026-10-03"),
            _identity(exam_id="exam-b", exam_date="2026-10-20"),
        ],
    )
    # 同为 10 月的两场统一练习仍歧义，不因某一天更接近而选择。
    assert result.state == "AMBIGUOUS"


def test_grade_aliases_and_unified_type_normalization():
    result = match_exam_identity(
        _identity(),
        [_identity(grade="九年级", exam_type="unified_practice", exam_type_label="统一练习")],
    )
    assert result.state == "EXACT_MATCH"


def test_unknown_type_labels_must_match():
    header = _identity(exam_type="other", exam_type_label="阶段检测")
    same = match_exam_identity(header, [_identity(exam_type="other", exam_type_label="阶段检测")])
    different = match_exam_identity(header, [_identity(exam_type="other", exam_type_label="模拟考试")])
    assert same.state == "EXACT_MATCH"
    assert different.state == "CONFLICT"


def test_missing_core_fields_are_needs_review():
    header = _identity(grade=None, exam_date=None)
    result = match_exam_identity(header, [_identity()])
    assert result.state == "NEEDS_REVIEW"
    assert "grade" in result.missing_fields
    assert "exam_date" in result.missing_fields


def test_candidate_without_exam_date_cannot_exact_match():
    result = match_exam_identity(_identity(), [_identity(exam_date=None)])
    assert result.state in {"NEEDS_REVIEW", "CONFLICT"}
    assert result.best_exam_id is None


def test_no_candidates_is_not_found():
    result = match_exam_identity(_identity(), [])
    assert result.state == "NOT_FOUND"


def test_near_month_and_date_are_not_auto_merge_evidence():
    result = match_exam_identity(
        _identity(exam_date="2026-10"),
        [
            _identity(exam_id="exam-near", exam_date="2026-11-01"),
            _identity(exam_id="exam-far", exam_date="2026-09-30"),
        ],
    )
    assert result.state == "CONFLICT"
    assert all(not candidate.exact for candidate in result.candidates)
