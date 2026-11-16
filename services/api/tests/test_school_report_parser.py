"""纯文本报告解析核心：不依赖真实 PDF，不访问网络。"""

from __future__ import annotations

from shutong.school_report_parser import classify_report_text, parse_report_text


def _report_text() -> str:
    return """—— 第 1 页 ——
2026-2027学年初三第一学期期中考试(虚构校区)
朝阳1班匿名分析报告册
报告时间: 2026年11月15日 10:00:00
报告单位: 虚构测试学校

—— 第 2 页 ——
总分成绩分析
成绩单
科目 满分 班级 得分 班排 年排 班级最高分 年级最高分
数学 100 朝阳1班 69 13 434 85 97
英语 100 朝阳1班 72.5 16 525 93 100
物理 70 朝阳1班 27 23 604 62 69
道德与法治 70 朝阳1班 48 22 592 68 70
总分 440 朝阳1班 216.5 16 544 295 329

—— 第 3 页 ——
数学成绩分析
成绩单
班级 原始分 班排 年排 班级最高分 年级最高分
朝阳1班 69 13 434 85 97
小题分析表
22（1） 主观题 一般 4 2 50%
22（2） 主观题 一般 4 4 100%
默写 主观题 容易 6 4 66.67%

—— 第 4 页 ——
数学答题卡
"""


def test_classifies_report_without_filename():
    assert classify_report_text(_report_text())[0] == "exam_analysis_report"


def test_totals_subjects_and_scope_difference():
    report = parse_report_text(_report_text(), digest="d" * 64)
    assert report.identity.academic_year == "2026-2027"
    assert report.identity.grade == "9"
    assert report.identity.exam_type == "期中考试"
    assert report.report_total_score == 216.5
    assert report.report_total_max == 440
    assert report.total_class_rank == 16
    assert report.listed_subject_score == 216.5
    assert report.listed_subject_max == 340
    assert report.scope_status == "DIFFERENT_SCOPE_POSSIBLE"
    assert {item.subject: (item.score, item.max_score) for item in report.subjects} == {
        "math": (69, 100),
        "english": (72.5, 100),
        "physics": (27, 70),
        "ethics": (48, 70),
    }


def test_complex_question_numbers_are_not_merged():
    report = parse_report_text(_report_text(), digest="d" * 64)
    numbers = {(item.subject, item.number) for item in report.questions}
    assert ("math", "22（1）") in numbers
    assert ("math", "22（2）") in numbers
    assert ("math", "默写") in numbers
    assert len([item for item in report.questions if item.number.startswith("22")]) == 2


def test_answer_card_page_is_associated_with_last_subject():
    report = parse_report_text(_report_text(), digest="d" * 64)
    assert report.answer_card_pages == {"math": [4]}


def test_pii_is_redacted_from_excerpt_and_title():
    text = _report_text() + "\n姓名：张三 学号：20250101 李四同学 王五分析报告册"
    report = parse_report_text(text, digest="d" * 64)
    for name in ("张三", "李四", "王五", "20250101", "朝阳1班"):
        assert name not in report.text_excerpt
        assert name not in (report.identity.title or "")
