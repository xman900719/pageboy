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


def test_wrapped_continuation_score_table_and_total_highest():
    wrapped = """—— 第 1 页 ——
2026-2027学年秋学期统一练习一
朝阳1班匿名分析报告册
报告时间: 2026年10月12日 10:00:00

—— 第 2 页 ——
总分成绩分析
成绩单
科目 满分 班级 得分 班排 年排 实考人数 班级最高分
语文 100 朝阳1班 63 17 548 677 84
数学 100 朝阳1班 70 14 433 677 86
英语 100 朝阳1班 71 17 510 675 93
物理 70 朝阳1班 36 21 582 678 62
道德与法治 50 朝阳1班 33 12 487 684 40
总分 370 朝阳1班 240 15 538 674 312
成绩单
科目 年级最高分 得分率
语文 96 63%
数学 100 70%
英语 98 71%
物理 69 51.43%
道德与法治 50 66%
总分 350 64.86%
"""
    report = parse_report_text(wrapped, digest="f" * 64)
    assert report.total_class_rank == 15
    assert report.total_grade_rank == 538
    assert report.total_participants == 674
    assert report.total_class_highest == 312.0
    assert report.total_grade_highest == 350.0
    by_subj = {item.subject: item for item in report.subjects}
    assert by_subj["chinese"].class_highest == 84.0
    assert by_subj["chinese"].grade_highest == 96.0
    assert by_subj["chinese"].score_rate == 63.0
    assert by_subj["math"].grade_highest == 100.0
    assert by_subj["physics"].participants == 678
    assert by_subj["physics"].grade_highest == 69.0


def test_tsv_unclosed_quote_sequential_repair_and_ocr_score_reconcile(tmp_path):
    """TSV 含未闭合引号不吞行，且顺延修复截断/重复题号、形近满分与漏识得分。"""
    from pathlib import Path
    from shutong.school_report_ocr import _line_words, table_rows
    from shutong.school_report_parser import (
        ReportQuestion,
        _norm_number,
        _reconcile_question_scores,
        _repair_sequential_question_numbers,
        parse_report_text,
    )

    # 1) TSV 含未闭合引号 '"1' 不得吞并第 11、12 行
    tsv_path = tmp_path / "page.tsv"
    tsv_rows = [
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
        "5\t1\t1\t1\t1\t1\t132\t400\t30\t20\t95\t小题",
        "5\t1\t1\t1\t1\t2\t322\t400\t30\t20\t95\t题型",
        "5\t1\t1\t1\t1\t3\t509\t400\t30\t20\t95\t难度",
        "5\t1\t1\t1\t1\t4\t696\t400\t30\t20\t95\t满分",
        "5\t1\t1\t1\t1\t5\t884\t400\t30\t20\t95\t得分",
        "5\t1\t1\t1\t1\t6\t1059\t400\t40\t20\t95\t得分率",
        "5\t1\t1\t1\t2\t1\t142\t450\t20\t20\t95\t10",
        "5\t1\t1\t1\t2\t2\t311\t450\t40\t20\t95\t主观题",
        "5\t1\t1\t1\t2\t3\t500\t450\t40\t20\t95\t一般",
        "5\t1\t1\t1\t2\t4\t711\t450\t10\t20\t95\t2",
        "5\t1\t1\t1\t2\t5\t898\t450\t10\t20\t95\t2",
        "5\t1\t1\t1\t2\t6\t1066\t450\t40\t20\t95\t100%",
        '5\t1\t1\t1\t3\t1\t142\t500\t20\t20\t95\t"1',
        "5\t1\t1\t1\t3\t2\t311\t500\t40\t20\t95\t主观题",
        "5\t1\t1\t1\t3\t3\t500\t500\t40\t20\t95\t一般",
        "5\t1\t1\t1\t3\t4\t711\t500\t10\t20\t95\t2",
        "5\t1\t1\t1\t3\t5\t898\t500\t10\t20\t95\t2",
        "5\t1\t1\t1\t3\t6\t1066\t500\t40\t20\t95\t100%",
        "5\t1\t1\t1\t4\t1\t142\t550\t20\t20\t95\t12",
        "5\t1\t1\t1\t4\t2\t311\t550\t40\t20\t95\t主观题",
        "5\t1\t1\t1\t4\t3\t500\t550\t40\t20\t95\t一般",
        "5\t1\t1\t1\t4\t4\t711\t550\t10\t20\t95\t2",
        "5\t1\t1\t1\t4\t5\t898\t550\t10\t20\t95\t2",
        "5\t1\t1\t1\t4\t6\t1066\t550\t40\t20\t95\t100%",
    ]
    tsv_path.write_text("\n".join(tsv_rows) + "\n", encoding="utf-8")
    from shutong.school_report_ocr import _group_lines

    parsed_rows = table_rows({"lines": _group_lines(_line_words(Path(tsv_path)))}, ("小题", "题型", "难度", "满分", "得分", "得分率"))
    assert [r["小题"] for r in parsed_rows] == ["10", "1", "12"]

    # 2) 顺延修复：10,1,12 -> 11; 14,16,17(重复16) -> 15; 16,7,18 -> 17
    sample_qs = [
        ReportQuestion("math", "1", "单选题", "容易", 2, 2, 100, 1),
        ReportQuestion("math", "7", "单选题", "一般", 2, 2, 100, 1),
        ReportQuestion("math", "10", "主观题", "一般", 2, 2, 100, 1),
        ReportQuestion("math", "1", "主观题", "一般", 2, 2, 100, 1),
        ReportQuestion("math", "12", "主观题", "一般", 2, 2, 100, 1),
        ReportQuestion("math", "16", "主观题", "一般", 2, 1, 50, 1),
        ReportQuestion("math", "7", "主观题", "一般", 5, 5, 100, 1),
        ReportQuestion("math", "18", "主观题", "一般", 8, 8, 100, 1),
        ReportQuestion("chinese", "16", "单选题", "容易", 2, 2, 100, 2),
        ReportQuestion("chinese", "14", "主观题", "一般", 3, 1, 33.33, 2),
        ReportQuestion("chinese", "16", "主观题", "较难", 5, 2, 40, 2),
        ReportQuestion("chinese", "17", "主观题", "较难", 2, 1, 50, 2),
    ]
    repaired = _repair_sequential_question_numbers(sample_qs)
    assert [q.number for q in repaired if q.subject == "math"] == ["1", "7", "10", "11", "12", "16", "17", "18"]
    assert [q.number for q in repaired if q.subject == "chinese"] == ["16", "14", "15", "17"]

    # 3) 形近字“了”->7、漏识得分按得分率反推、满分误识校正
    assert _norm_number("了") == 7.0
    assert _reconcile_question_scores(4.0, None, 25.0) == (4.0, 1.0)
    assert _reconcile_question_scores(8.0, 1.0, 33.33) == (3.0, 1.0)

    # 4) 逐字空格标题识别
    spaced_heading = _report_text().replace("数学成绩分析", "数 学 成 绩 分 析")
    parsed_spaced = parse_report_text(spaced_heading, digest="e" * 64)
    assert any(q.subject == "math" for q in parsed_spaced.questions)


def test_parse_report_pdf_preserves_answer_card_pages_when_tsv_ocr_drops_keywords(monkeypatch):
    from shutong import private_files as files
    from shutong import school_report_ocr as report_ocr
    from shutong.school_report_parser import parse_report_pdf

    full_text = _report_text()
    monkeypatch.setattr(files, "parse_text", lambda data, media_type: (full_text, "test"))
    # 模拟逐词 OCR 丢掉“小题分析表/成绩单/总结建议”完整词组且页内文本为空散
    fake_pages = [
        {"page": 1, "lines": [{"text": "分析报告册", "words": []}]},
        {"page": 2, "lines": [{"text": "数学 100 88 5 35", "words": []}]},
        {"page": 3, "lines": [{"text": "数学", "words": []}]},
        {"page": 4, "lines": [{"text": "作答区", "words": []}]},
    ]
    monkeypatch.setattr(report_ocr, "ocr_pdf", lambda data: (fake_pages, 4))
    monkeypatch.setattr(report_ocr, "table_rows", lambda page, cols: [])

    doc = parse_report_pdf(b"%PDF-1.4\n%fake\n", filename="report.pdf", digest="f" * 64)
    assert doc.answer_card_pages == {"math": [4]}
