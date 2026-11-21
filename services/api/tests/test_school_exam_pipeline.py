"""ST-EXAM-AUTOSYNC-01：本地卷流水线、严格匹配、私有归档与本人排名快照测试。"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from shutong import school_exam_pipeline as pipeline
from shutong.k12100_backfill import sanitize_k12100_bundle_for_storage

REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_AUTH = {"Authorization": "Bearer test-admin-secret"}
STUDENT_AUTH = {"Authorization": "Bearer test-student-secret"}


def _docx_bytes(lines: list[str]) -> bytes:
    from io import BytesIO

    xml_lines = "".join(
        f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in lines
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{xml_lines}</w:body></w:document>"
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def _header_lines(
    *,
    school: str = "虚构测试数据实验学校",
    academic_year: str = "2025—2026",
    term: str = "第一学期",
    grade: str = "九年级",
    exam_type: str = "10月月考",
    subject: str = "数学",
    exam_date: str = "2025年10月12日",
) -> list[str]:
    return [
        school,
        f"{academic_year}学年{term} {grade}{exam_type}",
        f"{subject}试卷",
        "姓名：张三 学号：20250101 考号：110101",
        f"考试时间：{exam_date}",
    ]


def _prepare_home(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("PAGEBOY_HOME", str(tmp_path / "pageboy-home"))
    monkeypatch.setenv("SHUTONG_ENV", "development")
    monkeypatch.setenv("SHUTONG_PRIVATE_DIR", str(tmp_path / "private"))
    inbox = pipeline.ensure_inbox("development")
    assert inbox.stat().st_mode & 0o777 == 0o700
    return inbox


def _write_paper(inbox: Path, name: str, lines: list[str]) -> Path:
    path = inbox / name
    path.write_bytes(_docx_bytes(lines))
    os.chmod(path, 0o600)
    return path


def _create_exam(client, **overrides) -> dict:
    payload = {
        "subject": "math",
        "title": "虚构测试数据 · 九上10月月考",
        "exam_date": "2025-10-12",
        "earned_points": 0,
        "max_points": 100,
        "confirmed_by_user": False,
        "school_name": "虚构测试数据实验学校",
        "grade": "九年级",
        "exam_type": "monthly",
        "academic_year": "2025-2026",
        "term": "first",
        "series_title": "2025—2026学年第一学期 九年级10月月考",
    }
    payload.update(overrides)
    response = client.post("/api/school-exams", json=payload, headers=ADMIN_AUTH)
    assert response.status_code == 201, response.text
    return response.json()


def test_scan_exact_match_import_and_rescan_are_idempotent(tmp_path, client, monkeypatch):
    inbox = _prepare_home(tmp_path, monkeypatch)
    exam = _create_exam(client)
    paper_path = _write_paper(inbox, "九年级数学月考试卷.docx", _header_lines())
    original = paper_path.read_bytes()

    status = client.get("/api/school-exams/sync-center", headers=ADMIN_AUTH)
    assert status.status_code == 200, status.text
    assert status.json()["source"]["real_source_configured"] is False
    assert status.json()["source"]["source_code"] == "SOURCE_NOT_CONFIGURED"

    scanned = client.post("/api/school-exams/pipeline/scan", json={}, headers=ADMIN_AUTH)
    assert scanned.status_code == 200, scanned.text
    body = scanned.json()
    assert body["run"]["discovered_count"] == 1
    assert body["run"]["needs_review_count"] == 0
    assert body["papers"][0]["match_state"] == "EXACT_MATCH"
    assert body["papers"][0]["school_exam_id"] == exam["id"]
    header = body["papers"][0]["header"]
    assert header["subject"] == "math"
    assert header["confidence"] == "high"
    assert "张三" not in header["text_excerpt"]
    assert "20250101" not in header["text_excerpt"]
    assert "storage_key" not in body["papers"][0]

    imported = client.post(
        f"/api/school-exams/pipeline/papers/{body['papers'][0]['id']}/import",
        headers=ADMIN_AUTH,
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["attachment_created"] is True
    again = client.post(
        f"/api/school-exams/pipeline/papers/{body['papers'][0]['id']}/import",
        headers=ADMIN_AUTH,
    )
    assert again.status_code == 200 and again.json()["already_imported"] is True
    detail = client.get(f"/api/school-exams/{exam['id']}", headers=ADMIN_AUTH).json()
    assert len(detail["attachments"]) == 1
    assert detail["earned_points"] == 0
    assert detail["confirmed_by_user"] is False

    rescanned = client.post("/api/school-exams/pipeline/scan", json={}, headers=ADMIN_AUTH)
    assert rescanned.status_code == 200
    assert rescanned.json()["run"]["duplicate_count"] == 1
    assert rescanned.json()["run"]["discovered_count"] == 1
    assert rescanned.json()["papers"][0]["status"] == "imported"
    assert paper_path.read_bytes() == original
    assert (inbox / paper_path.name).exists()


def test_rematch_reanalyzes_legacy_header_fields(tmp_path, client, monkeypatch):
    inbox = _prepare_home(tmp_path, monkeypatch)
    _create_exam(client)
    _write_paper(inbox, "九年级数学月考试卷.docx", _header_lines())
    paper = client.post("/api/school-exams/pipeline/scan", json={}, headers=ADMIN_AUTH).json()["papers"][0]

    from shutong.database import get_db
    from shutong.main import app
    from shutong import models as m

    session = next(app.dependency_overrides[get_db]())
    try:
        stored = session.get(m.SchoolExamPaper, paper["id"])
        stored.header_fields = {
            "subject": "math",
            "school_name": None,
            "term": None,
            "series_title": None,
            "exam_type": None,
            "exam_date": None,
            "complete": False,
            "fields": {
                "school_name": {"status": "missing", "value": None, "evidence": "无识别依据"},
                "term": {"status": "missing", "value": None, "evidence": "无识别依据"},
                "exam_type": {"status": "missing", "value": None, "evidence": "无识别依据"},
                "exam_date": {"status": "missing", "value": None, "evidence": "无识别依据"},
            },
            "warnings": ["字段缺失: school_name", "字段缺失: term", "字段缺失: exam_type", "字段缺失: exam_date"],
        }
        stored.header_confidence = "low"
        session.commit()

        public = pipeline._paper_header_public(stored)
        assert set(public["fields"]) == {"academic_year", "grade", "exam_type", "subject", "exam_date"}
        assert "school_name" not in "；".join(public["warnings"])
        assert "term" not in "；".join(public["warnings"])
    finally:
        session.close()

    rematched = client.post(
        f"/api/school-exams/pipeline/papers/{paper['id']}/match",
        json={},
        headers=ADMIN_AUTH,
    )
    assert rematched.status_code == 200, rematched.text
    body = rematched.json()["paper"]
    assert body["header"]["exam_type"] == "monthly"
    assert body["header"]["exam_date"] == "2025-10-12"
    assert set(body["header"]["fields"]) == {"academic_year", "grade", "exam_type", "subject", "exam_date"}


def test_same_month_multiple_unified_practice_is_blocked(tmp_path, client, monkeypatch):
    inbox = _prepare_home(tmp_path, monkeypatch)
    for suffix, exam_date in (("A", "2026-10-15"), ("B", "2026-10-20")):
        _create_exam(
            client,
            subject="ethics",
            title=f"虚构测试数据 · 九年级统一练习 {suffix}",
            exam_date=exam_date,
            school_name="虚构测试数据实验学校",
            grade="9",
            exam_type="unified_practice",
            exam_type_label="统一练习",
            academic_year="2026-2027",
            series_title="2026—2027学年度九年级统一练习",
        )
    _write_paper(
        inbox,
        "九年级道德与法治统一练习.docx",
        _header_lines(
            academic_year="2026—2027",
            term="",
            grade="九年级",
            exam_type="统一练习",
            subject="道德与法治",
            exam_date="2026年10月",
        ),
    )

    scanned = client.post("/api/school-exams/pipeline/scan", json={}, headers=ADMIN_AUTH)
    assert scanned.status_code == 200, scanned.text
    paper = scanned.json()["papers"][0]
    assert paper["header"]["exam_date"] == "2026-10"
    assert paper["header"]["exam_type"] == "unified_practice"
    assert paper["match_state"] == "AMBIGUOUS"
    assert paper["school_exam_id"] is None
    assert paper["status"] == "needs_review"
    blocked = client.post(
        f"/api/school-exams/pipeline/papers/{paper['id']}/import",
        headers=ADMIN_AUTH,
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "SCHOOL_EXAM_MATCH_REQUIRED"


def test_ambiguous_candidates_require_manual_choice(tmp_path, client, monkeypatch):
    inbox = _prepare_home(tmp_path, monkeypatch)
    first = _create_exam(client, title="虚构测试数据 · 同名月考 A")
    second = _create_exam(client, title="虚构测试数据 · 同名月考 B")
    _write_paper(inbox, "九年级数学月考试卷.docx", _header_lines())
    scanned = client.post("/api/school-exams/pipeline/scan", json={}, headers=ADMIN_AUTH).json()
    paper = scanned["papers"][0]
    assert paper["match_state"] == "AMBIGUOUS"
    assert paper["school_exam_id"] is None

    chosen = client.post(
        f"/api/school-exams/pipeline/papers/{paper['id']}/match",
        json={"exam_id": second["id"], "confirmed_by_human": True},
        headers=ADMIN_AUTH,
    )
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["paper"]["match_state"] == "MANUAL_CONFIRMED"
    assert chosen.json()["paper"]["school_exam_id"] == second["id"]
    imported = client.post(
        f"/api/school-exams/pipeline/papers/{paper['id']}/import",
        headers=ADMIN_AUTH,
    )
    assert imported.status_code == 200
    assert first["id"] != second["id"]


def test_manual_match_requires_flag_and_subject(tmp_path, client, monkeypatch):
    inbox = _prepare_home(tmp_path, monkeypatch)
    exam = _create_exam(client, school_name=None, grade=None, exam_type=None, academic_year=None, term=None, series_title=None)
    _write_paper(inbox, "九年级数学月考试卷.docx", _header_lines())
    paper = client.post("/api/school-exams/pipeline/scan", json={}, headers=ADMIN_AUTH).json()["papers"][0]
    assert paper["match_state"] in {"NOT_FOUND", "NEEDS_REVIEW"}

    no_flag = client.post(
        f"/api/school-exams/pipeline/papers/{paper['id']}/match",
        json={"exam_id": exam["id"]},
        headers=ADMIN_AUTH,
    )
    assert no_flag.status_code == 422
    assert no_flag.json()["detail"] == "HUMAN_CONFIRMATION_REQUIRED"

    chinese = _create_exam(client, subject="chinese", title="虚构测试数据 · 语文")
    wrong_subject = client.post(
        f"/api/school-exams/pipeline/papers/{paper['id']}/match",
        json={"exam_id": chinese["id"], "confirmed_by_human": True},
        headers=ADMIN_AUTH,
    )
    assert wrong_subject.status_code == 409
    assert wrong_subject.json()["detail"] == "SCHOOL_EXAM_SUBJECT_MISMATCH"

    matched = client.post(
        f"/api/school-exams/pipeline/papers/{paper['id']}/match",
        json={"exam_id": exam["id"], "confirmed_by_human": True},
        headers=ADMIN_AUTH,
    )
    assert matched.status_code == 200
    imported = client.post(
        f"/api/school-exams/pipeline/papers/{paper['id']}/import",
        headers=ADMIN_AUTH,
    )
    assert imported.status_code == 200
    metadata_updates = imported.json()["metadata_updates"]
    assert "grade" in metadata_updates
    assert "school_name" not in metadata_updates
    assert "term" not in metadata_updates
    assert "series_title" not in metadata_updates
    detail = client.get(f"/api/school-exams/{exam['id']}", headers=ADMIN_AUTH).json()
    assert detail["school_name"] is None
    assert detail["term"] is None
    assert detail["series_title"] is None
    assert detail["exam_date"] == "2025-10-12"


def test_scan_blocks_symlinks_corruption_and_wide_permissions(tmp_path, client, monkeypatch):
    inbox = _prepare_home(tmp_path, monkeypatch)
    outside = tmp_path / "outside.docx"
    outside.write_bytes(_docx_bytes(_header_lines()))
    os.symlink(outside, inbox / "symlink.docx")
    (inbox / "broken.pdf").write_bytes(b"not a real pdf")
    scanned = client.post("/api/school-exams/pipeline/scan", json={}, headers=ADMIN_AUTH)
    assert scanned.status_code == 200
    run = scanned.json()["run"]
    assert run["discovered_count"] == 1
    assert run["invalid_count"] == 1
    assert run["error_count"] >= 2
    codes = {item["code"] for item in run["errors"]}
    assert {"SYMLINK_REJECTED", "FILE_TYPE_MISMATCH"} <= codes
    assert scanned.json()["papers"] == []

    os.chmod(inbox, 0o755)
    try:
        blocked = client.post("/api/school-exams/pipeline/scan", json={}, headers=ADMIN_AUTH)
        assert blocked.status_code == 409
        assert blocked.json()["detail"] == "INBOX_PERMISSIONS_TOO_WIDE"
    finally:
        os.chmod(inbox, 0o700)


def test_pipeline_auth_is_admin_only(client):
    for path in (
        "/api/school-exams/sync-center",
        "/api/school-exams/pipeline/acquire",
    ):
        method = client.get if path.endswith("sync-center") else client.post
        assert method(path).status_code == 401
        assert method(path, headers=STUDENT_AUTH).status_code == 403
    assert client.post("/api/school-exams/pipeline/scan", json={}, headers=STUDENT_AUTH).status_code == 403
    blocked = client.post("/api/school-exams/pipeline/acquire", json={}, headers=ADMIN_AUTH)
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "SOURCE_NOT_CONFIGURED"


def test_rank_extraction_persistence_idempotency_and_profile_isolation(client, auth, student_auth, tmp_path, monkeypatch):
    monkeypatch.setenv("PAGEBOY_HOME", str(tmp_path / "pageboy-home"))
    monkeypatch.setenv("SHUTONG_ENV", "development")
    _create_exam(
        client,
        title="虚构测试数据 · 九上10月月考",
        earned_points=88,
        max_points=100,
        confirmed_by_user=True,
    )
    bundle = {
        "examName": "2025—2026学年第一学期 九年级10月月考",
        "examDate": "2025-10-12",
        "schoolName": "虚构测试数据实验学校",
        "gradeName": "九年级",
        "examTypeName": "月考",
        "academicYear": "2025-2026",
        "termName": "第一学期",
        "subjects": [
            {
                "subjectName": "数学",
                "score": 70,
                "fullScore": 100,
                "classRank": "5/320",
                "schoolRank": 18,
                "gradeStudentNum": "320人",
                "examNum": 320,
                "rank_ownership": "verified",
                "rank_ownership_basis": "single_student_ref_authenticated_subject_response",
                "students": [
                    {"studentName": "虚构测试数据另一名学生", "studentId": "S-OTHER", "classRank": 1},
                ],
                "smallQuestions": [{"questionName": "1", "score": 2, "fullScore": 2}],
            }
        ],
    }
    response = client.post(
        "/api/school-exams/k12100-sync/import-bundle",
        json={"bundle": bundle, "target_exam_date": "2025-10-12", "use_ai": False},
        headers=auth,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    row = body["subjects"][0]
    assert row["match_state"] == "EXACT_MATCH"
    assert row["score_status"] == "locked_conflict"
    assert row["earned_points"] == 88.0
    assert row["ranks_created"] == 2
    assert body["totals"]["ranks_created"] == 2
    assert body["knowledge_evidence_created"] == 0

    exam_id = row["exam_id"]
    ranks = client.get(f"/api/school-exams/{exam_id}/ranks", headers=auth).json()
    by_scope = {item["scope"]: item for item in ranks["ranks"]}
    assert by_scope["class"]["rank_value"] == 5
    assert by_scope["class"]["participant_count"] == 320
    assert by_scope["school"]["rank_value"] == 18
    assert by_scope["school"]["participant_count"] == 320
    assert set(ranks["missing_scopes"]) == {"grade", "region"}
    assert all(item["review_status"] == "pending" for item in ranks["ranks"])
    assert all(item["ownership_status"] == "verified" for item in ranks["ranks"])
    assert all(item["ownership_basis"] == "single_student_ref_authenticated_subject_response" for item in ranks["ranks"])

    # 相同数据重复同步不产生重复排名；锁定总分仍保持原值。
    repeat = client.post(
        "/api/school-exams/k12100-sync/import-bundle",
        json={"bundle": bundle, "target_exam_date": "2025-10-12", "use_ai": False},
        headers=auth,
    ).json()
    assert repeat["totals"]["ranks_created"] == 0
    repeated_ranks = client.get(f"/api/school-exams/{exam_id}/ranks", headers=auth).json()
    assert len(repeated_ranks["ranks"]) == 2
    assert all(item["history_count"] == 1 for item in repeated_ranks["ranks"])

    # 无效/冲突排名只报告问题，不写 0 或猜测值。
    bad_bundle = json.loads(json.dumps(bundle))
    bad_bundle["subjects"][0]["classRank"] = 0
    del bad_bundle["subjects"][0]["schoolRank"]
    bad = client.post(
        "/api/school-exams/k12100-sync/import-bundle",
        json={"bundle": bad_bundle, "target_exam_date": "2025-10-12", "use_ai": False},
        headers=auth,
    ).json()
    assert bad["subjects"][0]["ranks_created"] == 0
    assert any(item["code"] == "RANK_VALUE_INVALID" for item in bad["subjects"][0]["rank_issues"])
    assert len(client.get(f"/api/school-exams/{exam_id}/ranks", headers=auth).json()["ranks"]) == 2

    # 排名不进入学生端画像；学生令牌不能读取排名或确认排名。
    assert client.get("/api/guidance/profile?subject=math", headers=student_auth).json()["knowledge"] == []
    rank_id = by_scope["class"]["id"]
    assert client.get(f"/api/school-exams/{exam_id}/ranks", headers=student_auth).status_code == 403
    assert client.post(
        f"/api/school-exams/{exam_id}/ranks/{rank_id}/confirm",
        json={"confirmed_by_human": True},
        headers=student_auth,
    ).status_code == 403

    no_flag = client.post(
        f"/api/school-exams/{exam_id}/ranks/{rank_id}/confirm",
        json={"confirmed_by_human": False},
        headers=auth,
    )
    assert no_flag.status_code == 422
    confirmed = client.post(
        f"/api/school-exams/{exam_id}/ranks/{rank_id}/confirm",
        json={"confirmed_by_human": True},
        headers=auth,
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["review_status"] == "confirmed"
    assert confirmed.json()["rank_value"] == 5


def test_new_external_total_defaults_to_pending_review(client, auth, tmp_path, monkeypatch):
    monkeypatch.setenv("PAGEBOY_HOME", str(tmp_path / "pageboy-home"))
    monkeypatch.setenv("SHUTONG_ENV", "development")
    response = client.post(
        "/api/school-exams/k12100-sync/import-bundle",
        json={
            "bundle": {
                "examName": "虚构测试数据：默认待核对月考",
                "examDate": "2025-12-01",
                "schoolName": "虚构测试数据实验学校",
                "gradeName": "九年级",
                "examTypeName": "月考",
                "academicYear": "2025-2026",
                "termName": "第一学期",
                "subjects": [
                    {
                        "subjectName": "数学",
                        "score": 80,
                        "fullScore": 100,
                        "smallQuestions": [{"questionName": "1", "score": 2, "fullScore": 2}],
                    }
                ],
            },
            "use_ai": False,
        },
        headers=auth,
    )
    assert response.status_code == 200, response.text
    row = response.json()["subjects"][0]
    assert row["match_state"] == "NOT_FOUND"
    assert row["score_status"] == "created_unconfirmed"
    assert row["confirmed_by_user"] is False


def test_cli_dry_run_is_read_only(tmp_path, monkeypatch):
    source = tmp_path / "authorized-source"
    source.mkdir()
    (source / "九年级数学月考试卷.docx").write_bytes(_docx_bytes(_header_lines()))
    home = tmp_path / "cli-home"
    environment = dict(
        os.environ,
        PAGEBOY_HOME=str(home),
        SHUTONG_ENV="development",
        PYTHONPATH=str(REPO_ROOT / "services" / "api"),
    )
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "school_exam_pipeline.py"),
        "scan",
        "--env",
        "development",
        "--source-dir",
        str(source),
        "--dry-run",
        "--json",
    ]
    result = subprocess.run(command, cwd=REPO_ROOT, env=environment, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["file_count"] == 1
    assert payload["papers"][0]["header"]["subject"] == "math"
    assert not (home / "development" / "data" / "school-exams").exists()
    assert not (home / "development" / "data" / "shutong-dev.sqlite3").exists()
    assert (source / "九年级数学月考试卷.docx").exists()


def test_cli_stage_source_preserves_original_and_rejects_symlink(tmp_path, monkeypatch):
    monkeypatch.setenv("PAGEBOY_HOME", str(tmp_path / "pageboy-home"))
    monkeypatch.setenv("SHUTONG_ENV", "development")
    monkeypatch.setenv("SHUTONG_PRIVATE_DIR", str(tmp_path / "private"))
    source = tmp_path / "source"
    source.mkdir()
    paper = source / "九年级数学月考试卷.docx"
    paper.write_bytes(_docx_bytes(_header_lines()))
    outside = tmp_path / "outside.docx"
    outside.write_bytes(_docx_bytes(_header_lines(school="虚构测试数据外部学校")))
    os.symlink(outside, source / "escape.docx")

    staged = pipeline.stage_local_source(source, environment="development")
    assert staged["staged_count"] == 1
    assert any(item["code"] == "SYMLINK_REJECTED" for item in staged["errors"])
    assert paper.exists()
    inbox_files = list(pipeline.school_exam_inbox("development").iterdir())
    assert len(inbox_files) == 1
    assert inbox_files[0].stat().st_mode & 0o777 == 0o600


def test_cli_sanitizer_keeps_only_structured_self_rank_whitelist():
    raw = {
        "examName": "虚构测试数据 · 排名导出",
        "studName": "虚构测试数据学生",
        "exams": [
            {
                "examName": "虚构测试数据 · 排名导出",
                "examDate": "2025-10-12",
                "subjects": [
                    {
                        "subjectName": "数学",
                        "score": 90,
                        "fullScore": 100,
                        "schoolRank": 18,
                        "classRank": "5/320",
                        "schoolStudentNum": "320人",
                        "rank_ownership": "verified",
                        "rank_ownership_basis": "single_student_ref_authenticated_subject_response",
                        "students": [{"studentName": "其他学生", "studentId": "S-OTHER", "classRank": 1}],
                        "smallQuestions": [],
                    }
                ],
            }
        ],
    }
    clean = sanitize_k12100_bundle_for_storage(raw)
    serialized = json.dumps(clean, ensure_ascii=False)
    assert "schoolRank" not in serialized
    assert "classRank" not in serialized
    assert "其他学生" not in serialized
    assert "S-OTHER" not in serialized
    subject = clean["exams"][0]["subjects"][0]
    assert "students" not in subject
    assert {item["scope"] for item in subject["own_ranks"]} == {"class", "school"}
    assert subject["rank_ownership"] == "verified"
    assert next(item for item in subject["own_ranks"] if item["scope"] == "class")["rank_value"] == 5


def test_k12100_conflict_blocks_writes_instead_of_creating_duplicate(client, auth, tmp_path, monkeypatch):
    monkeypatch.setenv("PAGEBOY_HOME", str(tmp_path / "pageboy-home"))
    monkeypatch.setenv("SHUTONG_ENV", "development")
    existing = _create_exam(
        client,
        title="虚构测试数据 · 同日旧档",
        school_name=None,
        grade=None,
        exam_type=None,
        academic_year=None,
        term=None,
        series_title=None,
    )
    response = client.post(
        "/api/school-exams/k12100-sync/import-bundle",
        json={
            "bundle": {
                "examName": "虚构测试数据 · 同日另一场",
                "examDate": "2025-10-12",
                "schoolName": "虚构测试数据另一所学校",
                "gradeName": "九年级",
                "examTypeName": "月考",
                "academicYear": "2025-2026",
                "termName": "第一学期",
                "subjects": [
                    {
                        "subjectName": "数学",
                        "score": 70,
                        "fullScore": 100,
                        "smallQuestions": [{"questionName": "1", "score": 2, "fullScore": 2}],
                    }
                ],
            },
            "use_ai": False,
        },
        headers=auth,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    row = body["subjects"][0]
    assert row["score_status"] == "match_blocked"
    assert row["match_state"] in {"CONFLICT", "NEEDS_REVIEW"}
    assert body["totals"]["subjects_blocked"] == 1
    assert body["totals"]["created_exams"] == 0
    assert body["totals"]["drafts_created"] == 0
    exams = client.get("/api/school-exams?subject=math", headers=auth).json()
    assert len(exams) == 1 and exams[0]["id"] == existing["id"]
    detail = client.get(f"/api/school-exams/{existing['id']}", headers=auth).json()
    assert detail["earned_points"] == 0
    assert detail["items"] == []


def test_same_filename_different_content_is_not_deduplicated(tmp_path, client, monkeypatch):
    inbox = _prepare_home(tmp_path, monkeypatch)
    (inbox / "甲班").mkdir()
    (inbox / "乙班").mkdir()
    first = inbox / "甲班" / "同名试卷.docx"
    second = inbox / "乙班" / "同名试卷.docx"
    first.write_bytes(_docx_bytes(_header_lines(exam_type="10月月考")))
    second.write_bytes(_docx_bytes(_header_lines(exam_type="期中考试")))
    copy = inbox / "副本_同名内容.docx"
    copy.write_bytes(first.read_bytes())

    scanned = client.post("/api/school-exams/pipeline/scan", json={}, headers=ADMIN_AUTH)
    assert scanned.status_code == 200, scanned.text
    body = scanned.json()
    assert body["run"]["discovered_count"] == 3
    assert body["run"]["duplicate_count"] == 1
    assert len(body["papers"]) == 3
    hashes = {paper["sha256"] for paper in body["papers"]}
    assert len(hashes) == 2
    assert all(paper["status"] == "needs_review" for paper in body["papers"])
    assert any(paper["header"]["exam_type"] == "midterm" for paper in body["papers"])


def test_missing_header_enters_needs_review_without_match(tmp_path, client, monkeypatch):
    inbox = _prepare_home(tmp_path, monkeypatch)
    _create_exam(client)
    (inbox / "九年级数学试卷.docx").write_bytes(_docx_bytes(["数学试卷", "姓名：张三"]))
    scanned = client.post("/api/school-exams/pipeline/scan", json={}, headers=ADMIN_AUTH)
    assert scanned.status_code == 200
    paper = scanned.json()["papers"][0]
    assert paper["status"] == "needs_review"
    assert paper["match_state"] == "NEEDS_REVIEW"
    assert paper["school_exam_id"] is None
    assert paper["header"]["complete"] is False
    assert paper["header"]["confidence"] == "low"
    assert "字段缺失" in "；".join(paper["header"]["warnings"])


def test_source_directory_cannot_read_other_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("PAGEBOY_HOME", str(tmp_path / "pageboy-home"))
    monkeypatch.setenv("SHUTONG_ENV", "development")
    monkeypatch.setenv("SHUTONG_PRIVATE_DIR", str(tmp_path / "private"))
    production_source = tmp_path / "pageboy-home" / "production" / "data" / "school-exams" / "inbox"
    production_source.mkdir(parents=True)
    (production_source / "九年级数学月考试卷.docx").write_bytes(_docx_bytes(_header_lines()))

    with pytest.raises(pipeline.PaperPipelineError) as exc:
        pipeline.stage_local_source(production_source, environment="development")
    assert exc.value.code == "CROSS_ENVIRONMENT_SOURCE_REJECTED"
    with pytest.raises(Exception):
        # 生产目录属于另一环境，开发预演必须 fail-closed。
        pipeline.preview_local_source(production_source, environment="development")


def test_failed_scan_then_retry_recovers_without_duplicate_archive(tmp_path, client, monkeypatch):
    inbox = _prepare_home(tmp_path, monkeypatch)
    exam = _create_exam(client)
    broken = inbox / "九年级数学月考试卷.pdf"
    broken.write_bytes(b"%PDF-1.4 broken")
    failed = client.post("/api/school-exams/pipeline/scan", json={}, headers=ADMIN_AUTH).json()
    assert failed["run"]["invalid_count"] == 1
    assert failed["papers"] == []

    broken.unlink()
    _write_paper(inbox, "九年级数学月考试卷.docx", _header_lines())
    retried = client.post("/api/school-exams/pipeline/scan", json={}, headers=ADMIN_AUTH)
    assert retried.status_code == 200
    paper = retried.json()["papers"][0]
    assert paper["status"] == "matched"
    assert paper["school_exam_id"] == exam["id"]
    imported = client.post(
        f"/api/school-exams/pipeline/papers/{paper['id']}/import",
        headers=ADMIN_AUTH,
    )
    assert imported.status_code == 200
    rescanned = client.post("/api/school-exams/pipeline/scan", json={}, headers=ADMIN_AUTH).json()
    assert rescanned["run"]["duplicate_count"] == 1
    detail = client.get(f"/api/school-exams/{exam['id']}", headers=ADMIN_AUTH).json()
    assert len(detail["attachments"]) == 1


def test_r2_real_header_sample_matches_unique_unified_practice(tmp_path, client, monkeypatch):
    inbox = _prepare_home(tmp_path, monkeypatch)
    exam = _create_exam(
        client,
        subject="ethics",
        title="2026—2027学年度九年级统一练习 · 道德与法治",
        exam_date="2026-10-15",
        school_name=None,
        grade="9",
        exam_type="unified_practice",
        exam_type_label="统一练习",
        academic_year="2026-2027",
        term=None,
        series_title=None,
    )
    _write_paper(
        inbox,
        "九年级道德与法治统一练习.docx",
        ["2026～2027 学年度九年级统一练习", "道德与法治", "2026.10", "姓名：张三"],
    )
    scanned = client.post("/api/school-exams/pipeline/scan", json={}, headers=ADMIN_AUTH)
    assert scanned.status_code == 200, scanned.text
    paper = scanned.json()["papers"][0]
    assert paper["header"]["academic_year"] == "2026-2027"
    assert paper["header"]["grade"] == "9"
    assert paper["header"]["exam_type"] == "unified_practice"
    assert paper["header"]["exam_date"] == "2026-10"
    assert "exam_month" not in paper["header"]
    assert "date_precision" not in paper["header"]
    assert set(paper["header"]["fields"]) == {"academic_year", "grade", "exam_type", "subject", "exam_date"}
    assert paper["match_state"] == "EXACT_MATCH"
    assert paper["school_exam_id"] == exam["id"]


def test_unverified_rank_ownership_is_isolated_not_persisted(client, auth, tmp_path, monkeypatch):
    monkeypatch.setenv("PAGEBOY_HOME", str(tmp_path / "pageboy-home"))
    monkeypatch.setenv("SHUTONG_ENV", "development")
    exam = _create_exam(client, earned_points=88, max_points=100, confirmed_by_user=True)
    bundle = {
        "examName": "虚构测试数据 · 十月月考",
        "examDate": "2025-10-12",
        "schoolName": "虚构测试数据实验学校",
        "gradeName": "九年级",
        "examTypeName": "月考",
        "academicYear": "2025-2026",
        "subjects": [
            {
                "subjectName": "数学",
                "score": 70,
                "fullScore": 100,
                "classRank": 5,
                "rank_ownership": "unverified",
                "smallQuestions": [],
            }
        ],
    }
    response = client.post(
        "/api/school-exams/k12100-sync/import-bundle",
        json={"bundle": bundle, "target_exam_date": "2025-10-12", "use_ai": False},
        headers=auth,
    )
    assert response.status_code == 200, response.text
    row = response.json()["subjects"][0]
    assert row["score_status"] == "locked_conflict"
    assert row["ranks_created"] == 0
    assert any(issue["code"] == "RANK_OWNERSHIP_UNVERIFIED" for issue in row["rank_issues"])
    ranks = client.get(f"/api/school-exams/{exam['id']}/ranks", headers=auth).json()
    assert ranks["ranks"] == []


def test_k12100_missing_date_never_creates_today_archive(client, auth, tmp_path, monkeypatch):
    monkeypatch.setenv("PAGEBOY_HOME", str(tmp_path / "pageboy-home"))
    monkeypatch.setenv("SHUTONG_ENV", "development")
    response = client.post(
        "/api/school-exams/k12100-sync/import-bundle",
        json={
            "bundle": {
                "examName": "虚构测试数据 · 无日期统一练习",
                "subjects": [
                    {
                        "subjectName": "道德与法治",
                        "score": 80,
                        "fullScore": 100,
                        "smallQuestions": [],
                    }
                ],
            },
            "use_ai": False,
        },
        headers=auth,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["subjects"][0]["score_status"] == "match_blocked"
    assert body["subjects"][0]["match_state"] == "AWAITING_EXAM_DATE"
    assert body["subjects"][0]["exam_id"] == ""
    assert "未提供可验证" in body["subjects"][0]["warning"]
    assert client.get("/api/school-exams?subject=ethics", headers=auth).json() == []


def test_paper_collection_endpoint_is_scoped_and_never_confirms_totals(
    tmp_path, client, monkeypatch
):
    from shutong import k12100_backfill as kb

    inbox = _prepare_home(tmp_path, monkeypatch)
    exam = _create_exam(client)
    _write_paper(inbox, "九年级数学月考试卷.docx", _header_lines())
    paper = client.post("/api/school-exams/pipeline/scan", json={}, headers=ADMIN_AUTH).json()["papers"][0]
    assert paper["match_state"] == "EXACT_MATCH"
    imported = client.post(
        f"/api/school-exams/pipeline/papers/{paper['id']}/import",
        headers=ADMIN_AUTH,
    )
    assert imported.status_code == 200

    captured: dict = {}

    def _fake_start(db, **kwargs):
        captured.update(kwargs)
        return {"job_id": "job-paper-scope", "state": "queued", "stage_message": "任务已入队"}

    monkeypatch.setattr(kb, "start_k12100_sync_job", _fake_start)
    response = client.post(
        f"/api/school-exams/pipeline/papers/{paper['id']}/collect",
        json={"use_ai": False, "headless": False},
        headers=ADMIN_AUTH,
    )
    assert response.status_code == 202, response.text
    assert response.json()["job_id"] == "job-paper-scope"
    assert captured["owner"] == "owner"
    assert captured["max_exams"] == 1
    assert captured["confirm_total_scores"] is False
    assert captured["target_exam_date"] is None
    assert captured["headless"] is False
    assert captured["exam_keyword"] is None
    assert exam["id"]


def test_unmatched_paper_collection_is_blocked(tmp_path, client, monkeypatch):
    inbox = _prepare_home(tmp_path, monkeypatch)
    _write_paper(inbox, "九年级数学月考试卷.docx", _header_lines())
    paper = client.post("/api/school-exams/pipeline/scan", json={}, headers=ADMIN_AUTH).json()["papers"][0]
    assert paper["school_exam_id"] is None
    response = client.post(
        f"/api/school-exams/pipeline/papers/{paper['id']}/collect",
        json={},
        headers=ADMIN_AUTH,
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "SCHOOL_EXAM_MATCH_REQUIRED"


def test_cli_collection_helper_uses_matched_paper_and_waits(monkeypatch):
    import importlib.util

    cli_path = REPO_ROOT / "scripts" / "school_exam_pipeline.py"
    spec = importlib.util.spec_from_file_location("school_exam_cli_r2", cli_path)
    assert spec and spec.loader
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    calls: list[tuple[str, dict | None]] = []

    def _fake_request(base_url, path, token, *, method="GET", body=None, timeout=240):
        calls.append((path, body))
        if path.endswith("/collect"):
            return {"job_id": "job-r2", "state": "queued"}
        if "/k12100-sync/jobs/" in path:
            return {"job_id": "job-r2", "state": "completed", "result": {"totals": {"ranks_created": 2}}}
        raise AssertionError(path)

    monkeypatch.setattr(cli, "_api_request", _fake_request)
    job = cli.start_matched_paper_collection(
        "http://127.0.0.1:18765",
        "test-admin-secret",
        [{"id": "paper-1", "status": "imported", "school_exam_id": "exam-1"}],
        timeout=5,
    )
    assert job["state"] == "completed"
    assert calls[0][0] == "/api/school-exams/pipeline/papers/paper-1/collect"
    assert calls[0][1] == {"use_ai": True, "headless": False}
    assert calls[1][0] == "/api/school-exams/k12100-sync/jobs/job-r2"

    with pytest.raises(RuntimeError, match="NO_MATCHED_PAPER"):
        cli.start_matched_paper_collection("http://127.0.0.1:18765", "t", [])
    with pytest.raises(RuntimeError, match="MULTIPLE_MATCHED_PAPERS"):
        cli.start_matched_paper_collection(
            "http://127.0.0.1:18765",
            "t",
            [
                {"id": "paper-1", "status": "matched", "school_exam_id": "exam-1"},
                {"id": "paper-2", "status": "imported", "school_exam_id": "exam-2"},
            ],
        )


def test_header_date_ignores_question_body_dates():
    from shutong.school_exam_headers import recognize_header_text

    text = "\n".join(
        [
            "2026~2027 学年度第一学期九年级期中练习",
            "道德与法治",
            "总分: 70分 时间: 70分钟",
            "判断题 (共 10 题)",
            "2026.11",
            "1. 某校开展实践活动。",
            "2. 2020 年 6 月，某地发生了一件事。",
            "3. 2021 年 5 月 1 日，另一件事。",
            "4. 2022 年 2 月 4 日，冬奥会开幕。",
            "5. 继续作答。",
            "6. 继续作答。",
            "7. 继续作答。",
            "8. 题干中的 2023 年 3 月 3 日不应作为考试日期。",
        ]
    )
    result = recognize_header_text(text, "道法卷.pdf")
    assert result.exam_date == "2026-11"
    assert result.exam_type == "midterm"


def test_school_exam_accepts_month_only_date(client):
    response = client.post(
        "/api/school-exams",
        json={
            "subject": "math",
            "title": "虚构测试数据 · 月精度考试",
            "exam_date": "2026-10",
            "earned_points": 0,
            "max_points": 100,
            "confirmed_by_user": False,
        },
        headers=ADMIN_AUTH,
    )
    assert response.status_code == 201, response.text
    rows = client.get("/api/school-exams?subject=math", headers=ADMIN_AUTH).json()
    created = next(row for row in rows if row["id"] == response.json()["id"])
    assert created["exam_date"].startswith("2026-10")


def test_delete_single_school_exam_requires_confirmation_and_cascades(tmp_path, client, monkeypatch):
    _prepare_home(tmp_path, monkeypatch)
    exam = _create_exam(client)

    from shutong.database import get_db
    from shutong.main import app
    from shutong import models as m
    from sqlalchemy import select

    session = next(app.dependency_overrides[get_db]())
    try:
        session.add(
            m.SchoolExamItem(
                school_exam_id=exam["id"],
                question_label="1",
                knowledge_id="math.demo",
                earned_points=1,
                max_points=2,
                scoring_origin="manual_entry",
                confirmed_by_user=True,
            )
        )
        session.add(
            m.SchoolExamRankSnapshot(
                school_exam_id=exam["id"],
                learner_id="owner",
                scope="total",
                rank_value=1,
                source_field="rank",
                content_hash="hash-delete-test",
            )
        )
        from shutong import private_files as files

        blob = files.write_blob(b"delete-me-attachment")
        session.add(
            m.SchoolPaperAttachment(
                school_exam_id=exam["id"],
                owner_id="owner",
                filename="删除测试附件.pdf",
                media_type="application/pdf",
                sha256="0" * 64,
                byte_size=22,
                storage_key=blob,
            )
        )
        session.commit()
    finally:
        session.close()

    no_confirm = client.delete(f"/api/school-exams/{exam['id']}", headers=ADMIN_AUTH)
    assert no_confirm.status_code == 400
    assert no_confirm.json()["detail"] == "SCHOOL_EXAM_DELETE_CONFIRMATION_REQUIRED"

    deleted = client.delete(f"/api/school-exams/{exam['id']}?confirm=true", headers=ADMIN_AUTH)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] is True
    assert deleted.json()["items_deleted"] == 1
    assert deleted.json()["attachments_deleted"] == 1
    assert deleted.json()["rank_snapshots_deleted"] == 1
    assert files.blob_path(blob).exists() is False
    assert client.get(f"/api/school-exams/{exam['id']}", headers=ADMIN_AUTH).status_code == 404

    session = next(app.dependency_overrides[get_db]())
    try:
        assert session.execute(select(m.SchoolExamItem).where(m.SchoolExamItem.school_exam_id == exam["id"])).first() is None
        assert session.execute(select(m.SchoolExamRankSnapshot).where(m.SchoolExamRankSnapshot.school_exam_id == exam["id"])).first() is None
    finally:
        session.close()


def test_rematch_recovers_missing_private_blob_from_inbox(tmp_path, client, monkeypatch):
    inbox = _prepare_home(tmp_path, monkeypatch)
    _create_exam(client)
    _write_paper(inbox, "九年级数学月考试卷.docx", _header_lines())
    paper = client.post("/api/school-exams/pipeline/scan", json={}, headers=ADMIN_AUTH).json()["papers"][0]

    from shutong import private_files as files

    # 公开响应不含 storage_key，用数据库记录定位实际 blob。
    from shutong.database import get_db
    from shutong.main import app
    from shutong import models as m

    session = next(app.dependency_overrides[get_db]())
    try:
        stored = session.get(m.SchoolExamPaper, paper["id"])
        old_blob = files.blob_path(stored.storage_key)
        assert old_blob.is_file()
        old_blob.unlink()
    finally:
        session.close()

    rematched = client.post(
        f"/api/school-exams/pipeline/papers/{paper['id']}/match",
        json={},
        headers=ADMIN_AUTH,
    )
    assert rematched.status_code == 200, rematched.text
    assert rematched.json()["paper"]["header"]["complete"] is True

    session = next(app.dependency_overrides[get_db]())
    try:
        stored = session.get(m.SchoolExamPaper, paper["id"])
        assert files.blob_path(stored.storage_key).is_file()
        assert stored.storage_key != old_blob.name
    finally:
        session.close()
