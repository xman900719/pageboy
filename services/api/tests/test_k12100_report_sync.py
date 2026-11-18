"""ST-EXAM-AUTOSYNC R3：k12100「总分」分析报告自动下载与考试档案同步正反例测试（无真实联网，全部为虚构测试数据）。"""

from __future__ import annotations

from datetime import date
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import time

from PIL import Image
from sqlalchemy import select

from shutong import k12100_backfill as kb
from shutong import k12100_report_sync as rs
from shutong import models as m
from shutong import school_exam_matcher as matcher
from shutong import school_report_parser as parser
from shutong import school_report_pipeline as rp
from shutong.database import get_db
from shutong.main import app


def _valid_pdf_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (60, 40), (255, 255, 255)).save(buf, format="PDF")
    return buf.getvalue()


def _synthetic_doc(
    *,
    title: str = "虚构测试数据 2026-2027学年秋学期统一练习一",
    academic_year: str = "2026-2027",
    grade: str | None = None,
    exam_type: str = "统一练习一",
    digest: str = "a" * 64,
    math_score: float = 88.0,
    q1_score: float = 2.0,
    with_cards: bool = False,
) -> parser.ReportDocument:
    text = f"""—— 第 1 页 ——
{title}
{academic_year}学年{exam_type}
[已脱敏]分析报告册

—— 第 2 页 ——
总分成绩分析
成绩单
科目 满分 班级 得分 班排 年排 班级最高分 年级最高分
数学 100 朝阳1班 {math_score:g} 5 35 98 100
英语 100 朝阳1班 84 8 60 95 99
物理 70 朝阳1班 61 4 28 68 70
道德与法治 50 朝阳1班 44 6 40 49 50
总分 320 朝阳1班 {math_score + 189:g} 6 38 300 315

—— 第 3 页 ——
数学成绩分析
成绩单
班级 原始分 班排 年排 班级最高分 年级最高分
朝阳1班 {math_score:g} 5 35 98 100
小题分析表
1 单选题 容易 2 {q1_score:g} 100%
3 简答题 中等 5 3 60%
"""
    doc = parser.parse_report_text(text, digest=digest)
    doc.identity.grade = grade
    if with_cards:
        doc.answer_card_pages = {"math": [1]}
    return doc


def _setup_k12_env(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "k12cfg"
    cfg_dir.mkdir(mode=0o700)
    env_file = cfg_dir / "k12100.env"
    env_file.write_text("K12100_USERNAME=25999test\nK12100_PASSWORD=TopSecret999\n", encoding="utf-8")
    os.chmod(cfg_dir, 0o700)
    os.chmod(env_file, 0o600)
    monkeypatch.setenv("SHUTONG_K12100_CONFIG_DIR", str(cfg_dir))
    monkeypatch.setenv("SHUTONG_PRIVATE_DIR", str(tmp_path / "private"))
    fake_repo = tmp_path / "fake_repo"
    (fake_repo / "scripts").mkdir(parents=True)
    (fake_repo / "scripts" / "k12100_browser.mjs").write_text("// stub\n", encoding="utf-8")
    (fake_repo / "apps" / "web" / "node_modules" / "playwright-core").mkdir(parents=True)
    monkeypatch.setattr(kb, "resolve_repo_root", lambda *_args: fake_repo)
    monkeypatch.setattr(kb, "_is_isolated_container", lambda: False)
    monkeypatch.setattr(kb, "_find_node_binary", lambda: "/usr/local/bin/node")
    return cfg_dir


def _poll_job(client, auth, job_id: str) -> dict:
    for _ in range(60):
        resp = client.get(f"/api/school-exams/k12100-sync/jobs/{job_id}", headers=auth)
        assert resp.status_code == 200
        body = resp.json()
        if body["state"] in {"completed", "failed"}:
            return body
        time.sleep(0.05)
    raise AssertionError("job did not finish in time")


def test_report_sync_creates_exams_fills_grade_from_homepage_and_skips_synced(client, auth, student_auth, tmp_path, monkeypatch):
    assert client.post("/api/school-exams/k12100-sync/report-jobs", json={}, headers=student_auth).status_code == 403
    assert client.post("/api/school-exams/k12100-sync/report-jobs", json={}).status_code == 401

    _setup_k12_env(tmp_path, monkeypatch)
    pdf_bytes = _valid_pdf_bytes()
    doc = _synthetic_doc(grade=None, digest=sha256(pdf_bytes).hexdigest(), with_cards=True)
    monkeypatch.setattr(rp, "parse_report_pdf", lambda data, filename="", digest="": doc)
    # 模拟 pdftoppm 切出 1 张答题卡图
    img_buf = BytesIO()
    Image.new("RGB", (20, 20), (240, 240, 240)).save(img_buf, format="PNG")
    png_bytes = img_buf.getvalue()

    real_run = subprocess.run

    def _fake_run(cmd, **kwargs):
        if cmd and cmd[0] == "pdftoppm":
            prefix = Path(cmd[-1])
            prefix.with_name(f"{prefix.name}-1.png").write_bytes(png_bytes)
            return type("Res", (), {"returncode": 0, "stdout": b"", "stderr": b""})()
        return real_run(cmd, **kwargs)

    monkeypatch.setattr("subprocess.run", _fake_run)

    seen_skips: list[set[str]] = []

    def _fake_download(*, skip_exam_ids, download_dir, **_kwargs):
        seen_skips.append(set(skip_exam_ids))
        if "2109179122628517890" in skip_exam_ids:
            return {
                "status": "collected",
                "home_exams": [
                    {
                        "external_exam_id": "2109179122628517890",
                        "exam_name": "虚构测试数据 26-27学年统一练习一",
                        "exam_date": "2026-10-10",
                        "grade": "九年级",
                        "academic_year": "2026-2027",
                        "exam_type": "月考",
                        "already_synced": True,
                    }
                ],
                "downloads": [],
                "failures": [],
            }
        target_pdf = download_dir / "report_0.pdf"
        target_pdf.write_bytes(pdf_bytes)
        return {
            "status": "collected",
            "home_exams": [
                {
                    "external_exam_id": "2109179122628517890",
                    "exam_name": "虚构测试数据 26-27学年统一练习一",
                    "exam_date": "2026-10-10",
                    "grade": "九年级",
                    "academic_year": "2026-2027",
                    "exam_type": "月考",
                    "already_synced": False,
                }
            ],
            "downloads": [
                {
                    "external_exam_id": "2109179122628517890",
                    "exam_name": "虚构测试数据 26-27学年统一练习一",
                    "exam_date": "2026-10-10",
                    "grade": "九年级",
                    "academic_year": "2026-2027",
                    "exam_type": "月考",
                    "file": str(target_pdf),
                    "suggested_filename": "虚构测试数据_统一练习一_分析报告册.pdf",
                }
            ],
            "failures": [],
        }

    monkeypatch.setattr(rs, "_download_reports_with_browser", _fake_download)

    start = client.post("/api/school-exams/k12100-sync/report-jobs", json={"max_exams": 3, "headless": True}, headers=auth)
    assert start.status_code == 202, start.text
    assert start.json()["kind"] == "report"
    finished = _poll_job(client, auth, start.json()["job_id"])
    assert finished["state"] == "completed", finished
    rr = finished["report_result"]
    assert rr["totals"]["created_exams"] == 4
    assert rr["totals"]["drafts_created"] == 2
    assert rr["totals"]["cards_synced"] == 1
    assert rr["knowledge_evidence_created"] == 0

    math_exams = client.get("/api/school-exams?subject=math", headers=auth).json()
    assert len(math_exams) == 1
    ex = math_exams[0]
    assert ex["exam_date"] == "2026-10-10"
    assert ex["grade"] == "9"
    assert ex["academic_year"] == "2026-2027"
    assert ex["exam_type"] == "unified_practice"
    assert ex["exam_type_label"] == "统一练习"
    assert ex["external_exam_id"] == "2109179122628517890"
    assert ex["source_kind"] == "k12100"
    assert ex["confirmed_by_user"] is False
    assert ex["earned_points"] == 88.0

    # 新建档案应能被试卷五字段严格匹配命中
    match_res = matcher.match_exam_identity(
        matcher.ExamIdentity(
            exam_id=None,
            subject="math",
            exam_date="2026-10",
            grade="9",
            exam_type="unified_practice",
            exam_type_label="统一练习",
            academic_year="2026-2027",
        ),
        [matcher.ExamIdentity.from_dict({**ex, "subject": "math"})],
    )
    assert match_res.state == "EXACT_MATCH"
    assert match_res.best_exam_id == ex["id"]

    # 报告行上已补全年级和平台考试日期
    reports = client.get("/api/school-exams/reports", headers=auth).json()
    assert len(reports) == 1
    assert reports[0]["grade"] == "9"
    assert reports[0]["exam_date"] == "2026-10-10"
    assert reports[0]["external_exam_id"] == "2109179122628517890"

    # 逐题草稿为 ocr_draft 且未确认，不写能力画像
    detail = client.get(f"/api/school-exams/{ex['id']}", headers=auth).json()
    assert len(detail["items"]) == 2
    assert all(it["scoring_origin"] == "ocr_draft" and it["confirmed_by_user"] is False for it in detail["items"])
    assert len(detail["attachments"]) == 1

    # 二次执行自动跳过已有 external_exam_id
    second = client.post("/api/school-exams/k12100-sync/report-jobs", json={}, headers=auth)
    assert second.status_code == 202
    finished2 = _poll_job(client, auth, second.json()["job_id"])
    assert finished2["state"] == "completed"
    assert "2109179122628517890" in seen_skips[-1]
    assert finished2["report_result"]["totals"]["skipped_existing"] == 1
    assert finished2["report_result"]["totals"]["downloaded"] == 0

    # 清空内存任务记录（模拟服务重启/任务过期）并再次跳过后，sync-center.synced_reports 仍完整返回库中已同步报告与各科详情
    with kb._JOB_LOCK:  # noqa: SLF001
        kb._JOBS.clear()  # noqa: SLF001
        kb._JOB_ORDER.clear()  # noqa: SLF001
    assert client.get("/api/school-exams/sync-center", headers=student_auth).status_code == 403
    sync_center = client.get("/api/school-exams/sync-center", headers=auth)
    assert sync_center.status_code == 200, sync_center.text
    persisted = sync_center.json()["synced_reports"]
    assert len(persisted) == 1
    rep = persisted[0]
    assert rep["external_exam_id"] == "2109179122628517890"
    assert rep["exam_date"] == "2026-10-10"
    assert rep["grade"] == "9"
    assert len(rep["exams"]) == 4
    by_subj = {item["subject"]: item for item in rep["exams"]}
    assert by_subj["math"]["earned_points"] == 88.0
    assert by_subj["math"]["confirmed_by_user"] is False
    assert by_subj["math"]["draft_count"] == 2
    assert by_subj["math"]["attachment_count"] == 1
    assert "storage_key" not in json.dumps(persisted, ensure_ascii=False)


def test_report_sync_updates_unconfirmed_fills_manual_and_protects_locked(client, auth, tmp_path, monkeypatch):
    monkeypatch.setenv("SHUTONG_PRIVATE_DIR", str(tmp_path / "private"))
    # 1) 数学：手工月锚点建档（未确认、缺年级/学年/类型），含 1 条未确认草稿 + 1 条已确认小题
    created_math = client.post(
        "/api/school-exams",
        json={
            "subject": "math",
            "title": "虚构测试数据 · 26-27学年统一练习一",
            "exam_date": "2026-10",
            "earned_points": 0,
            "max_points": 100,
            "confirmed_by_user": False,
        },
        headers=auth,
    )
    assert created_math.status_code == 201
    math_id = created_math.json()["id"]

    # 2) 英语：已人工锁分且分数与报告不同 -> 必须触发 locked_conflict 不覆盖
    created_eng = client.post(
        "/api/school-exams",
        json={
            "subject": "english",
            "title": "虚构测试数据 · 26-27学年统一练习一",
            "exam_date": "2026-10-10",
            "earned_points": 90,
            "max_points": 100,
            "confirmed_by_user": True,
            "grade": "9",
            "exam_type": "unified_practice",
            "academic_year": "2026-2027",
        },
        headers=auth,
    )
    assert created_eng.status_code == 201

    # 3) 物理：非空年级冲突（库中为 8，报告为 9）-> identity_conflict 不覆盖
    created_phy = client.post(
        "/api/school-exams",
        json={
            "subject": "physics",
            "title": "虚构测试数据 · 26-27学年统一练习一",
            "exam_date": "2026-10-10",
            "earned_points": 50,
            "max_points": 70,
            "confirmed_by_user": False,
            "grade": "8",
            "exam_type": "unified_practice",
            "academic_year": "2026-2027",
        },
        headers=auth,
    )
    assert created_phy.status_code == 201

    session = next(app.dependency_overrides[get_db]())
    try:
        session.add(
            m.SchoolExamItem(
                school_exam_id=math_id,
                question_label="1",
                knowledge_id="math_01",
                earned_points=0.0,
                max_points=2.0,
                scoring_origin="ocr_draft",
                confirmed_by_user=False,
            )
        )
        session.add(
            m.SchoolExamItem(
                school_exam_id=math_id,
                question_label="3",
                knowledge_id="math_03",
                earned_points=5.0,
                max_points=5.0,
                scoring_origin="manual_entry",
                confirmed_by_user=True,
            )
        )
        session.commit()
    finally:
        session.close()

    pdf_bytes = _valid_pdf_bytes()
    pdf_file = tmp_path / "r.pdf"
    pdf_file.write_bytes(pdf_bytes)
    doc = _synthetic_doc(grade="9", digest=sha256(pdf_bytes).hexdigest(), math_score=86.5, q1_score=2.0)
    monkeypatch.setattr(rp, "parse_report_pdf", lambda data, filename="", digest="": doc)

    session = next(app.dependency_overrides[get_db]())
    try:
        res = rs.process_downloaded_reports(
            session,
            owner="owner",
            allowed_root=tmp_path,
            bundle={
                "status": "collected",
                "home_exams": [],
                "downloads": [
                    {
                        "external_exam_id": "E-1010",
                        "exam_name": "虚构测试数据 · 26-27学年统一练习一",
                        "exam_date": "2026-10-10",
                        "grade": "九年级",
                        "academic_year": "2026-2027",
                        "exam_type": "统一练习",
                        "file": str(pdf_file),
                        "suggested_filename": "虚构测试数据.pdf",
                    }
                ],
                "failures": [],
            },
        )
    finally:
        session.close()

    by_subj = {row["subject"]: row for row in res["subject_actions"]}
    assert by_subj["math"]["action"] == "updated"
    assert by_subj["math"]["earned_points"] == 86.5
    assert by_subj["math"]["confirmed_by_user"] is False
    assert set(by_subj["math"]["filled_fields"]) >= {"grade", "exam_type", "academic_year", "external_exam_id", "exam_date"}
    assert by_subj["english"]["action"] == "locked_conflict"
    assert by_subj["english"]["earned_points"] == 90.0
    assert by_subj["physics"]["action"] == "identity_conflict"
    assert by_subj["ethics"]["action"] == "created"

    math_detail = client.get(f"/api/school-exams/{math_id}", headers=auth).json()
    assert math_detail["exam_date"] == "2026-10-10"
    items_by_label = {it["question_label"]: it for it in math_detail["items"]}
    # 未确认草稿得分已更新，并保留了既有知识点编码
    assert items_by_label["1"]["earned_points"] == 2.0
    assert items_by_label["1"]["knowledge_id"] == "math_01"
    # 已人工确认的小题 3 保持 5 分未被报告的 3 分覆写
    assert items_by_label["3"]["earned_points"] == 5.0
    assert items_by_label["3"]["confirmed_by_user"] is True


def test_report_sync_month_format_missing_date_ambiguous_invalid_pdf_and_circuit_breaker(client, auth, tmp_path, monkeypatch):
    _setup_k12_env(tmp_path, monkeypatch)
    pdf_bytes = _valid_pdf_bytes()
    doc = _synthetic_doc(grade="9", digest=sha256(pdf_bytes).hexdigest())
    monkeypatch.setattr(rp, "parse_report_pdf", lambda data, filename="", digest="": doc)

    # A. k12100 仅给年月 YYYY-MM 格式时按 k12100 格式保存为 YYYY-MM（并锚定当月 1 日入库）
    month_pdf = tmp_path / "month.pdf"
    month_pdf.write_bytes(pdf_bytes)
    session = next(app.dependency_overrides[get_db]())
    try:
        month_res = rs.process_downloaded_reports(
            session,
            owner="owner",
            allowed_root=tmp_path,
            bundle={
                "status": "collected",
                "home_exams": [],
                "downloads": [
                    {
                        "external_exam_id": "E-MONTH",
                        "exam_name": "虚构测试数据 · 月格式",
                        "exam_date": "2026-11",
                        "grade": "9",
                        "academic_year": "2026-2027",
                        "exam_type": "统一练习一",
                        "file": str(month_pdf),
                    }
                ],
                "failures": [],
            },
        )
        assert month_res["totals"]["created_exams"] == 4
        assert month_res["reports"][0]["exam_date"] == "2026-11"
        created_math = session.execute(
            select(m.SchoolExam).where(m.SchoolExam.external_exam_id == "E-MONTH", m.SchoolExam.subject == "math")
        ).scalars().first()
        assert created_math is not None and created_math.exam_date == date(2026, 11, 1)
    finally:
        session.close()

    # B. k12100 完全没有考试日期 -> awaiting_exam_date，不建档；非 PDF / 路径越界 -> failure
    nodate_pdf = tmp_path / "nodate.pdf"
    nodate_pdf.write_bytes(pdf_bytes + b"\n%nodate")
    bad_file = tmp_path / "bad.pdf"
    bad_file.write_bytes(b"<html>not a pdf</html>")
    outside = tmp_path.parent / "outside.pdf"
    outside.write_bytes(pdf_bytes)
    doc2 = _synthetic_doc(title="虚构测试数据 · 无日期期中", exam_type="期中考试", grade="9", digest=sha256(nodate_pdf.read_bytes()).hexdigest())
    monkeypatch.setattr(rp, "parse_report_pdf", lambda data, filename="", digest="": doc2)

    session = next(app.dependency_overrides[get_db]())
    try:
        bad_res = rs.process_downloaded_reports(
            session,
            owner="owner",
            allowed_root=tmp_path,
            bundle={
                "status": "collected",
                "home_exams": [],
                "downloads": [
                    {
                        "external_exam_id": "E-NODATE",
                        "exam_name": "虚构测试数据 · 无日期期中",
                        "exam_date": "",
                        "grade": "9",
                        "academic_year": "2026-2027",
                        "exam_type": "期中考试",
                        "file": str(nodate_pdf),
                    },
                    {
                        "external_exam_id": "E-BADPDF",
                        "exam_name": "虚构测试数据 · 假PDF",
                        "exam_date": "2026-11-12",
                        "file": str(bad_file),
                    },
                    {
                        "external_exam_id": "E-ESCAPE",
                        "exam_name": "虚构测试数据 · 越界路径",
                        "exam_date": "2026-11-12",
                        "file": str(outside),
                    },
                ],
                "failures": [],
            },
        )
        assert bad_res["totals"]["awaiting_exam_date"] == 4
        assert bad_res["totals"]["created_exams"] == 0
        codes = {f["code"] for f in bad_res["failures"]}
        assert "K12100_REPORT_NOT_PDF" in codes
        assert "K12100_REPORT_FILE_MISSING" in codes

        # C. 多候选歧义不覆盖
        for idx in (1, 2):
            session.add(
                m.SchoolExam(
                    learner_id="owner",
                    subject="math",
                    exam_date=date(2026, 11, 12),
                    title=f"虚构测试数据 · 歧义期中 {idx}",
                    earned_points=60,
                    max_points=100,
                    confirmed_by_user=False,
                    grade="9",
                    exam_type="midterm",
                    academic_year="2026-2027",
                )
            )
        session.commit()
        ambig_pdf = tmp_path / "ambig.pdf"
        ambig_pdf.write_bytes(pdf_bytes + b"\n%ambig")
        doc3 = _synthetic_doc(title="虚构测试数据 · 歧义期中", exam_type="期中考试", grade="9", digest=sha256(ambig_pdf.read_bytes()).hexdigest())
        monkeypatch.setattr(rp, "parse_report_pdf", lambda data, filename="", digest="": doc3)
        ambig_res = rs.process_downloaded_reports(
            session,
            owner="owner",
            allowed_root=tmp_path,
            bundle={
                "status": "collected",
                "home_exams": [],
                "downloads": [
                    {
                        "external_exam_id": "E-AMBIG",
                        "exam_name": "虚构测试数据 · 歧义期中",
                        "exam_date": "2026-11-12",
                        "grade": "9",
                        "academic_year": "2026-2027",
                        "exam_type": "期中考试",
                        "file": str(ambig_pdf),
                    }
                ],
                "failures": [],
            },
        )
        assert ambig_res["totals"]["ambiguous_exams"] == 1
    finally:
        session.close()

    # D. 浏览器熔断 -> job failed 且零写入
    monkeypatch.setattr(
        rs,
        "_download_reports_with_browser",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("K12100_CIRCUIT_BREAKER: 上游返回 HTTP 429，已立即熔断")),
    )
    breaker_resp = client.post("/api/school-exams/k12100-sync/report-jobs", json={}, headers=auth)
    assert breaker_resp.status_code == 202
    failed_job = _poll_job(client, auth, breaker_resp.json()["job_id"])
    assert failed_job["state"] == "failed"
    assert failed_job["error_code"] == "K12100_CIRCUIT_BREAKER"
    assert failed_job["report_result"] is None


def test_report_sync_recovers_partial_downloads_and_resumes(client, auth, tmp_path, monkeypatch):
    """第 1 份下完后中途失败 -> 已下完的第 1 份照常入库并在 sync-center/failed-job 可见；重试自动续传第 2 份。"""
    _setup_k12_env(tmp_path, monkeypatch)
    monkeypatch.setenv("SHUTONG_K12100_ALLOW_NODE_WRAPPER", "1")
    pdf1 = _valid_pdf_bytes() + b"\n%partial-1"
    pdf2 = _valid_pdf_bytes() + b"\n%partial-2"
    doc1 = _synthetic_doc(title="虚构测试数据 · 阶段一", digest=sha256(pdf1).hexdigest(), math_score=82.0)
    doc2 = _synthetic_doc(title="虚构测试数据 · 阶段二", exam_type="期中考试", digest=sha256(pdf2).hexdigest(), math_score=91.0)
    docs_by_digest = {sha256(pdf1).hexdigest(): doc1, sha256(pdf2).hexdigest(): doc2}
    monkeypatch.setattr(rp, "parse_report_pdf", lambda data, filename="", digest="": docs_by_digest[digest])

    seen_skips: list[list[str]] = []
    call_idx = {"n": 0}
    real_run = subprocess.run

    def _fake_run(cmd, **kwargs):
        if cmd and len(cmd) >= 2 and str(cmd[1]).endswith("k12100_browser.mjs"):
            call_idx["n"] += 1
            out_path = Path(cmd[cmd.index("--output") + 1])
            dl_dir = Path(cmd[cmd.index("--download-dir") + 1])
            skip_file = Path(cmd[cmd.index("--skip-file") + 1])
            skip_ids = json.loads(skip_file.read_text(encoding="utf-8"))["external_exam_ids"]
            seen_skips.append(skip_ids)

            if call_idx["n"] == 1:
                # 模拟下完第 1 份并实时写回 --output，但在第 2 份中途退出码=1
                p1 = dl_dir / "report_0_E-P1.pdf"
                p1.write_bytes(pdf1)
                out_path.write_text(
                    json.dumps(
                        {
                            "status": "interrupted",
                            "home_exams": [
                                {"external_exam_id": "E-P1", "exam_name": "虚构测试数据 阶段一", "exam_date": "2026-10-12", "grade": "9", "academic_year": "2026-2027", "exam_type": "月考", "already_synced": False},
                                {"external_exam_id": "E-P2", "exam_name": "虚构测试数据 阶段二", "exam_date": "2026-11-12", "grade": "9", "academic_year": "2026-2027", "exam_type": "期中", "already_synced": False},
                            ],
                            "downloads": [
                                {
                                    "external_exam_id": "E-P1",
                                    "exam_name": "虚构测试数据 阶段一",
                                    "exam_date": "2026-10-12",
                                    "grade": "9",
                                    "academic_year": "2026-2027",
                                    "exam_type": "月考",
                                    "file": str(p1),
                                    "suggested_filename": "阶段一.pdf",
                                }
                            ],
                            "failures": [],
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                return type("Res", (), {"returncode": 1, "stdout": "", "stderr": "simulated crash"})()

            # 第 2 次：应自动跳过 E-P1，仅下 E-P2
            p2 = dl_dir / "report_0_E-P2.pdf"
            p2.write_bytes(pdf2)
            out_path.write_text(
                json.dumps(
                    {
                        "status": "collected",
                        "home_exams": [
                            {"external_exam_id": "E-P1", "exam_name": "虚构测试数据 阶段一", "exam_date": "2026-10-12", "grade": "9", "academic_year": "2026-2027", "exam_type": "月考", "already_synced": "E-P1" in skip_ids},
                            {"external_exam_id": "E-P2", "exam_name": "虚构测试数据 阶段二", "exam_date": "2026-11-12", "grade": "9", "academic_year": "2026-2027", "exam_type": "期中", "already_synced": False},
                        ],
                        "downloads": [
                            {
                                "external_exam_id": "E-P2",
                                "exam_name": "虚构测试数据 阶段二",
                                "exam_date": "2026-11-12",
                                "grade": "9",
                                "academic_year": "2026-2027",
                                "exam_type": "期中",
                                "file": str(p2),
                                "suggested_filename": "阶段二.pdf",
                            }
                        ],
                        "failures": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            return type("Res", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        return real_run(cmd, **kwargs)

    monkeypatch.setattr("subprocess.run", _fake_run)

    # 1) 第一次中途中断：job 为 failed，但 E-P1 已入库且 report_result / sync-center 可见
    first = client.post("/api/school-exams/k12100-sync/report-jobs", json={}, headers=auth)
    assert first.status_code == 202
    res1 = _poll_job(client, auth, first.json()["job_id"])
    assert res1["state"] == "failed"
    assert res1["error_code"] == "K12100_BROWSER_FAILED"
    assert res1["report_result"] is not None
    assert res1["report_result"]["totals"]["reports_registered"] == 1
    assert res1["report_result"]["totals"]["created_exams"] == 4

    sc1 = client.get("/api/school-exams/sync-center", headers=auth).json()["synced_reports"]
    assert [r["external_exam_id"] for r in sc1] == ["E-P1"]
    assert len(sc1[0]["exams"]) == 4

    # 2) 第二次重试：skip_exam_ids 自动包含 E-P1，仅下 E-P2，最终 sync-center 共 2 场
    second = client.post("/api/school-exams/k12100-sync/report-jobs", json={}, headers=auth)
    assert second.status_code == 202
    res2 = _poll_job(client, auth, second.json()["job_id"])
    assert res2["state"] == "completed"
    assert "E-P1" in seen_skips[-1]
    assert res2["report_result"]["totals"]["skipped_existing"] == 1
    assert res2["report_result"]["totals"]["downloaded"] == 1

    sc2 = client.get("/api/school-exams/sync-center", headers=auth).json()["synced_reports"]
    assert {r["external_exam_id"] for r in sc2} == {"E-P1", "E-P2"}

    # 3) 反例：无有效下载文件（越界路径或空列表）的浏览器异常退出必须零写入
    def _empty_crash(cmd, **kwargs):
        if cmd and len(cmd) >= 2 and str(cmd[1]).endswith("k12100_browser.mjs"):
            out_path = Path(cmd[cmd.index("--output") + 1])
            out_path.write_text(
                json.dumps({"status": "interrupted", "home_exams": [], "downloads": [{"external_exam_id": "E-BAD", "file": "/etc/passwd"}], "failures": []}),
                encoding="utf-8",
            )
            return type("Res", (), {"returncode": 1, "stdout": "", "stderr": "empty crash"})()
        return real_run(cmd, **kwargs)

    monkeypatch.setattr("subprocess.run", _empty_crash)
    third = client.post("/api/school-exams/k12100-sync/report-jobs", json={}, headers=auth)
    res3 = _poll_job(client, auth, third.json()["job_id"])
    assert res3["state"] == "failed"
    assert res3["report_result"] is None
    assert len(client.get("/api/school-exams/sync-center", headers=auth).json()["synced_reports"]) == 2


def test_four_fixes_isolation_dedup_precheck_and_full_ranks_highest(client, auth, student_auth, tmp_path, monkeypatch):
    """覆盖：1. 分科核对独立 2. 下载前完整性预检与本地无网补全 3. 同场不同 SHA-256 报告与答题卡单次去重持久化 4. 总分+各科排名与班/年最高分全量同步。"""
    _setup_k12_env(tmp_path, monkeypatch)
    monkeypatch.setenv("SHUTONG_K12100_ALLOW_NODE_WRAPPER", "1")
    pdf_inbox = _valid_pdf_bytes() + b"\n%inbox-copy"
    pdf_k12 = _valid_pdf_bytes() + b"\n%k12100-copy"

    doc_inbox = parser.parse_report_text(
        """—— 第 1 页 ——
虚构测试数据 2026-2027学年初三秋学期统一练习一
朝阳1班匿名分析报告册
报告时间: 2026年10月11日 09:00:00
—— 第 2 页 ——
总分成绩分析
成绩单
科目 满分 班级 得分 班排 年排 实考人数 班级最高 年级最高
数学 100 朝阳1班 88 5 35 600 98 100
英语 100 朝阳1班 84 8 60 600 95 99
物理 70 朝阳1班 61 4 28 600 68 70
道德与法治 50 朝阳1班 44 6 40 600 49 50
总分 320 朝阳1班 277 6 38 600 301 318
—— 第 3 页 ——
数学成绩分析
小题分析表
1 单选题 容易 2 2 100%
""",
        digest=sha256(pdf_inbox).hexdigest(),
    )
    doc_inbox.answer_card_pages = {"math": [3]}

    doc_k12 = parser.parse_report_text(
        """—— 第 1 页 ——
虚构测试数据 2026-2027学年初三秋学期统一练习一
朝阳1班匿名分析报告册
报告时间: 2026年10月18日 12:00:00
—— 第 2 页 ——
总分成绩分析
成绩单
科目 满分 班级 得分 班排 年排 实考人数 班级最高 年级最高
数学 100 朝阳1班 88 5 35 600 98 100
英语 100 朝阳1班 84 8 60 600 95 99
物理 70 朝阳1班 61 4 28 600 68 70
道德与法治 50 朝阳1班 44 6 40 600 49 50
总分 320 朝阳1班 277 6 38 600 301 318
—— 第 4 页 ——
数学成绩分析
小题分析表
1 单选题 容易 2 2 100%
""",
        digest=sha256(pdf_k12).hexdigest(),
    )
    doc_k12.answer_card_pages = {"math": [4]}

    docs_map = {
        sha256(pdf_inbox).hexdigest(): doc_inbox,
        sha256(pdf_k12).hexdigest(): doc_k12,
    }
    monkeypatch.setattr(rp, "parse_report_pdf", lambda data, filename="", digest="": docs_map[digest or sha256(data).hexdigest()])

    img_buf = BytesIO()
    Image.new("RGB", (24, 24), (245, 245, 245)).save(img_buf, format="PNG")
    png_bytes = img_buf.getvalue()
    real_run = subprocess.run

    # A. 先以本地收件箱版本登记一次（无 external_exam_id），再以 k12100 另时间戳 PDF 下载同名场次 -> 必须合并为仅 1 条报告且仅保留 1 份答题卡
    session = next(app.dependency_overrides[get_db]())
    try:
        r_inbox, created1 = rp.register_report_bytes(
            session,
            owner="owner",
            data=pdf_inbox,
            filename="inbox_t1.pdf",
            source_ref="inbox/t1.pdf",
            platform_meta={"exam_date": "2026-10-10"},
        )
        assert created1 is True
        rp.upsert_exams_from_report(session, report=r_inbox, platform_meta={"exam_date": "2026-10-10"})
        # 模拟旧版只导入了考试和报告，但尚未写入任何排名快照与总分最高分的本地状态
        session.query(m.SchoolExamRankSnapshot).delete()
        r_inbox.total_class_highest = None
        r_inbox.total_grade_highest = None
        session.commit()
    finally:
        session.close()

    def _run_pdftoppm_or_k12(cmd, **kwargs):
        if cmd and cmd[0] == "pdftoppm":
            prefix = Path(cmd[-1])
            prefix.with_name(f"{prefix.name}-1.png").write_bytes(png_bytes)
            return type("Res", (), {"returncode": 0, "stdout": b"", "stderr": b""})()
        if cmd and len(cmd) >= 2 and str(cmd[1]).endswith("k12100_browser.mjs"):
            out_path = Path(cmd[cmd.index("--output") + 1])
            dl_dir = Path(cmd[cmd.index("--download-dir") + 1])
            skip_file = Path(cmd[cmd.index("--skip-file") + 1])
            skip_payload = json.loads(skip_file.read_text(encoding="utf-8"))
            if "E-DEDUP-1" in skip_payload["external_exam_ids"] or skip_payload["complete_identities"]:
                # 第二次启动前核对发现已完整 -> 首页即跳过，零下载
                out_path.write_text(
                    json.dumps(
                        {
                            "status": "collected",
                            "home_exams": [
                                {
                                    "external_exam_id": "E-DEDUP-1",
                                    "exam_name": "虚构测试数据 统一练习一",
                                    "exam_date": "2026-10-10",
                                    "grade": "九年级",
                                    "academic_year": "2026-2027",
                                    "exam_type": "统一练习一",
                                    "already_synced": True,
                                }
                            ],
                            "downloads": [],
                            "failures": [],
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                return type("Res", (), {"returncode": 0, "stdout": "", "stderr": ""})()

            p_k12 = dl_dir / "report_0_E-DEDUP-1.pdf"
            p_k12.write_bytes(pdf_k12)
            out_path.write_text(
                json.dumps(
                    {
                        "status": "collected",
                        "home_exams": [
                            {
                                "external_exam_id": "E-DEDUP-1",
                                "exam_name": "虚构测试数据 统一练习一",
                                "exam_date": "2026-10-10",
                                "grade": "九年级",
                                "academic_year": "2026-2027",
                                "exam_type": "统一练习一",
                                "already_synced": False,
                            }
                        ],
                        "downloads": [
                            {
                                "external_exam_id": "E-DEDUP-1",
                                "exam_name": "虚构测试数据 统一练习一",
                                "exam_date": "2026-10-10",
                                "grade": "九年级",
                                "academic_year": "2026-2027",
                                "exam_type": "统一练习一",
                                "file": str(p_k12),
                                "suggested_filename": "统一练习一.pdf",
                            }
                        ],
                        "failures": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            return type("Res", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        return real_run(cmd, **kwargs)

    monkeypatch.setattr("subprocess.run", _run_pdftoppm_or_k12)

    # 先调 hydrate-local：无需联网即完成排名与答题卡补全
    assert client.post("/api/school-exams/k12100-sync/hydrate-local", headers=student_auth).status_code == 403
    hydrated = client.post("/api/school-exams/k12100-sync/hydrate-local", headers=auth)
    assert hydrated.status_code == 200, hydrated.text
    h_json = hydrated.json()
    assert h_json["ranks_synced"] >= 8
    assert h_json["sync_readiness"]["all_complete"] is True
    assert len(h_json["synced_reports"]) == 1

    # 就算直接再下载同场不同 sha256 的 k12100 报告，也只保留 1 条规范报告记录，且排名/最高分全量在位
    session = next(app.dependency_overrides[get_db]())
    try:
        rep_k12, created2 = rp.register_report_bytes(
            session,
            owner="owner",
            data=pdf_k12,
            filename="k12_t1.pdf",
            source_ref="k12100/E-DEDUP-1",
            platform_meta={
                "external_exam_id": "E-DEDUP-1",
                "exam_date": "2026-10-10",
                "exam_name": "虚构测试数据 统一练习一",
                "grade": "9",
                "academic_year": "2026-2027",
                "exam_type": "统一练习一",
            },
        )
        assert created2 is False
        rp.upsert_exams_from_report(session, report=rep_k12, platform_meta={"exam_date": "2026-10-10", "external_exam_id": "E-DEDUP-1"})
        rp.build_answer_card_attachments(session, report=rep_k12, rotation=0)
        session.commit()
    finally:
        session.close()

    reports = client.get("/api/school-exams/reports", headers=auth).json()
    assert len(reports) == 1
    assert reports[0]["total_class_highest"] == 301.0
    assert reports[0]["total_grade_highest"] == 318.0

    # Bug 3 & 4：sync-center 仅 1 场报告、1 份答题卡，总分与各科排名/最高分齐全
    sc = client.get("/api/school-exams/sync-center", headers=auth).json()
    assert sc["sync_readiness"]["all_complete"] is True
    assert len(sc["synced_reports"]) == 1
    rep_view = sc["synced_reports"][0]
    assert rep_view["total_class_rank"] == 6
    assert rep_view["total_grade_rank"] == 38
    assert rep_view["total_class_highest"] == 301.0
    assert rep_view["total_grade_highest"] == 318.0
    assert rep_view["completeness"]["complete"] is True
    by_subj = {item["subject"]: item for item in rep_view["exams"]}
    assert by_subj["math"]["class_rank"] == 5
    assert by_subj["math"]["grade_rank"] == 35
    assert by_subj["math"]["class_highest"] == 98.0
    assert by_subj["math"]["grade_highest"] == 100.0
    assert by_subj["math"]["attachment_count"] == 1

    # 检查数学 /ranks 接口同时含本学科排名/最高分 + 全科总分排名/最高分
    math_id = by_subj["math"]["exam_id"]
    ranks_data = client.get(f"/api/school-exams/{math_id}/ranks", headers=auth).json()
    assert ranks_data["class_highest"] == 98.0
    assert ranks_data["grade_highest"] == 100.0
    assert {(r["scope"], r["rank_value"], r["highest_score"]) for r in ranks_data["ranks"]} == {
        ("class", 5, 98.0),
        ("grade", 35, 100.0),
    }
    assert {(r["scope"], r["rank_value"], r["highest_score"]) for r in ranks_data["total_ranks"]} == {
        ("class", 6, 301.0),
        ("grade", 38, 318.0),
    }

    # Bug 2：再点下载同步前先核对到已完整同步 -> 零重复下载
    job_resp = client.post("/api/school-exams/k12100-sync/report-jobs", json={}, headers=auth)
    assert job_resp.status_code == 202
    done = _poll_job(client, auth, job_resp.json()["job_id"])
    assert done["state"] == "completed"
    assert done["report_result"]["totals"]["downloaded"] == 0
    assert done["report_result"]["totals"]["skipped_existing"] == 1

    # Bug 1：只确认数学总分后，其余 3 科仍必须为 待核对 (confirmed_by_user=False)
    conf = client.post(f"/api/school-exams/{math_id}/confirm", json={"earned_points": 88, "confirmed_by_user": True}, headers=auth)
    assert conf.status_code == 200 and conf.json()["confirmed_by_user"] is True
    sc_after = client.get("/api/school-exams/sync-center", headers=auth).json()["synced_reports"][0]
    after_by_subj = {item["subject"]: item for item in sc_after["exams"]}
    assert after_by_subj["math"]["confirmed_by_user"] is True
    assert after_by_subj["english"]["confirmed_by_user"] is False
    assert after_by_subj["physics"]["confirmed_by_user"] is False
    assert after_by_subj["ethics"]["confirmed_by_user"] is False
    # 红线：排名与未核对草稿绝不进入学生能力画像
    assert client.get("/api/guidance/profile?subject=math", headers=student_auth).json()["knowledge"] == []
