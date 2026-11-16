"""分析报告册登记 API：不上传真实 PDF，不访问网络。"""

from __future__ import annotations

from pathlib import Path

from shutong import school_report_parser as parser
from shutong.school_report_pipeline import serialize_report
from shutong import school_report_pipeline as report_pipeline

ADMIN_AUTH = {"Authorization": "Bearer test-admin-secret"}

_SYNTHETIC = """—— 第 1 页 ——
2026-2027学年初三第一学期期中考试(虚构校区)
[已脱敏]分析报告册

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
1 单选题 容易 2 2 100%
"""


def _doc():
    return parser.parse_report_text(_SYNTHETIC, digest="a" * 64)


def test_report_scan_is_idempotent_and_owner_scoped(client, tmp_path, monkeypatch):
    inbox = tmp_path / "reports"
    inbox.mkdir()
    paper = inbox / "report.pdf"
    paper.write_bytes(b"%PDF-1.4 synthetic")
    doc = _doc()

    monkeypatch.setattr(report_pipeline.papers, "ensure_inbox", lambda environment=None: inbox)
    monkeypatch.setattr(report_pipeline.papers, "iter_source_files", lambda source: ([paper], []))
    monkeypatch.setattr(report_pipeline.papers, "_read_validated_file", lambda path: (b"%PDF-1.4 synthetic", "application/pdf"))
    monkeypatch.setattr(report_pipeline, "parse_report_pdf", lambda data, filename="", digest="": doc)
    monkeypatch.setattr(report_pipeline.files, "write_blob", lambda data: "b" * 32)

    first = client.post("/api/school-exams/reports/scan", headers=ADMIN_AUTH)
    assert first.status_code == 200, first.text
    assert first.json()["discovered"] == 1
    report = first.json()["reports"][0]
    assert report["report_total_score"] == 216.5
    assert report["scope_status"] == "DIFFERENT_SCOPE_POSSIBLE"
    assert "storage_key" not in report

    second = client.post("/api/school-exams/reports/scan", headers=ADMIN_AUTH)
    assert second.status_code == 200
    assert second.json()["discovered"] == 1

    listed = client.get("/api/school-exams/reports", headers=ADMIN_AUTH)
    assert listed.status_code == 200 and len(listed.json()) == 1
    detail = client.get(f"/api/school-exams/reports/{report['id']}", headers=ADMIN_AUTH)
    assert detail.status_code == 200
    assert detail.json()["id"] == report["id"]

    student = client.get("/api/school-exams/reports", headers={"Authorization": "Bearer test-student-secret"})
    assert student.status_code in {401, 403}

    from shutong import models as m
    from shutong.database import get_db
    from shutong.main import app

    from io import BytesIO
    from PIL import Image

    blob = tmp_path / "card.png"
    image_bytes = BytesIO()
    Image.new("RGB", (10, 20), (255, 255, 255)).save(image_bytes, format="PNG")
    blob.write_bytes(image_bytes.getvalue())
    monkeypatch.setattr(report_pipeline.files, "blob_path", lambda key: blob)
    session = next(app.dependency_overrides[get_db]())
    try:
        session.add(
            m.SchoolExamReportAttachment(
                report_id=report["id"],
                learner_id="owner",
                subject="math",
                page_number=5,
                filename="答题卡-math-5.png",
                media_type="image/png",
                byte_size=len(blob.read_bytes()),
                storage_key="c" * 32,
                sha256="e" * 64,
                rotation=90,
            )
        )
        session.commit()
    finally:
        session.close()
    cards = client.get(f"/api/school-exams/reports/{report['id']}/answer-cards", headers=ADMIN_AUTH)
    assert cards.status_code == 200 and len(cards.json()) == 1
    image = client.get(
        f"/api/school-exams/reports/{report['id']}/answer-cards/{cards.json()[0]['id']}/image",
        headers=ADMIN_AUTH,
    )
    assert image.status_code == 200 and image.content.startswith(b"\x89PNG")
    with Image.open(BytesIO(image.content)) as rotated:
        assert rotated.size == (20, 10)

    no_match = client.post(f"/api/school-exams/reports/{report['id']}/confirm", json={"confirmed": True}, headers=ADMIN_AUTH)
    assert no_match.status_code == 409
    assert no_match.json()["detail"] == "REPORT_MATCH_REQUIRED"

    for subject in ("math", "english", "physics", "ethics"):
        created = client.post(
            "/api/school-exams",
            json={
                "subject": subject,
                "title": f"虚构测试数据 · 期中 {subject}",
                "exam_date": "2026-11-15",
                "earned_points": 0,
                "max_points": 100,
                "confirmed_by_user": False,
                "grade": "9",
                "exam_type": "midterm",
                "academic_year": "2026-2027",
            },
            headers=ADMIN_AUTH,
        )
        assert created.status_code == 201, created.text
    matched = client.post(f"/api/school-exams/reports/{report['id']}/match", headers=ADMIN_AUTH)
    assert matched.status_code == 200, matched.text
    assert matched.json()["match"]["match_state"] == "EXACT_MATCH"
    assert len(matched.json()["report"]["linked_exam_ids"]) == 4
    patched = client.patch(
        f"/api/school-exams/reports/{report['id']}",
        json={"grade": "9"},
        headers=ADMIN_AUTH,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["grade"] == "9"
    confirmed = client.post(f"/api/school-exams/reports/{report['id']}/confirm", json={"confirmed": True}, headers=ADMIN_AUTH)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"
    assert set(confirmed.json()["ledger"]["applied_subjects"]) == {"math", "english", "physics", "ethics"}
    drafts = client.post(f"/api/school-exams/reports/{report['id']}/items/drafts", headers=ADMIN_AUTH)
    assert drafts.status_code == 200, drafts.text
    assert drafts.json()["created"] == 1
    from shutong.database import get_db
    from shutong.main import app
    from shutong import models as m
    from sqlalchemy import select

    session = next(app.dependency_overrides[get_db]())
    try:
        items = session.execute(select(m.SchoolExamItem).where(m.SchoolExamItem.question_label == "1")).scalars().all()
        assert items and items[0].scoring_origin == "ocr_draft" and items[0].confirmed_by_user is False
        assert items[0].knowledge_id == "unmapped"
    finally:
        session.close()
    math_exams = client.get("/api/school-exams?subject=math", headers=ADMIN_AUTH).json()
    assert any(item["earned_points"] == 69 and item["max_points"] == 100 and item["confirmed_by_user"] for item in math_exams)


def test_subject_scan_skips_analysis_report(tmp_path, client, monkeypatch):
    inbox = _inbox = tmp_path / "papers"
    inbox.mkdir()
    path = inbox / "mixed.pdf"
    path.write_bytes(b"%PDF-1.4 synthetic")
    from shutong import school_exam_pipeline as pipeline
    from shutong.school_exam_headers import HeaderRecognition

    monkeypatch.setattr(pipeline, "ensure_inbox", lambda environment=None: inbox)
    monkeypatch.setattr(pipeline, "iter_source_files", lambda source: ([path], []))
    monkeypatch.setattr(pipeline, "_read_validated_file", lambda path: (b"%PDF-1.4 synthetic", "application/pdf"))
    monkeypatch.setattr(
        pipeline,
        "analyze_paper_bytes",
        lambda data, media_type, filename: HeaderRecognition(
            subject=None,
            academic_year=None,
            grade=None,
            exam_type=None,
            exam_type_label=None,
            exam_date=None,
            confidence="low",
            complete=False,
            text_excerpt="2026-2027 学年初三第一学期期中考试分析报告册",
        ),
    )
    monkeypatch.setattr(pipeline, "files", pipeline.files)
    result = pipeline.scan_local_papers(next(__import__("shutong.main", fromlist=["app"]).app.dependency_overrides[__import__("shutong.database", fromlist=["get_db"]).get_db]()), owner="owner")
    assert result["run"]["discovered_count"] == 1
    assert result["papers"] == []
