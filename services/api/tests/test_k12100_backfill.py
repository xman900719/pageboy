"""k12100.com 全科补全编排、SSRF 防护、PDF 提干与单任务互斥运行测试。"""

from __future__ import annotations

import base64
from io import BytesIO
import os
from pathlib import Path
import socket
import threading
import time

from fastapi import HTTPException
from PIL import Image
import pytest

from shutong import k12100_backfill as kb
from shutong import school_paper_parser as parser


def _make_valid_jpeg_bytes(color: tuple[int, int, int] = (230, 240, 250)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (64, 64), color=color).save(buf, format="JPEG")
    return buf.getvalue()


def _make_fake_pdf_with_text() -> bytes:
    # 构造极简合法单页含可读文字的 PDF 以便测试无 OCR 与本地 pdftotext 切分路径
    lines = [
        r"1. Calculate the value of \(-2\) + 5.",
        r"2. Find the vertex of y = \(x - 1\)^2 + 3.",
    ]
    stream_cmds = "BT /F1 12 Tf 72 720 Td (" + ") Tj T* (".join(lines) + ") Tj ET"
    stream_bytes = stream_cmds.encode("latin1")
    objs = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n",
        f"4 0 obj << /Length {len(stream_bytes)} >> stream\n".encode("latin1") + stream_bytes + b"\nendstream endobj\n",
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
    ]
    header = b"%PDF-1.4\n"
    offsets: list[int] = []
    body = bytearray()
    for obj in objs:
        offsets.append(len(header) + len(body))
        body.extend(obj)
    xref_pos = len(header) + len(body)
    xref = [f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode("latin1")]
    for off in offsets:
        xref.append(f"{off:010d} 00000 n \n".encode("latin1"))
    trailer = (
        f"trailer << /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n"
    ).encode("latin1")
    return header + bytes(body) + b"".join(xref) + trailer


def test_strip_pii_fields_and_ssrf_guardrails(monkeypatch):
    dirty = {
        "studName": "张三",
        "schoolRank": 5,
        "username": "25001",
        "nested": {"studentId": "S999", "examName": "虚构测试数据：统一练习"},
        "subjects": [{"subjectName": "英语", "token": "secret-tok", "score": 71}],
    }
    cleaned = kb.strip_pii_fields(dirty)
    assert "studName" not in cleaned
    assert "schoolRank" not in cleaned
    assert "username" not in cleaned
    assert "studentId" not in cleaned["nested"]
    assert "token" not in cleaned["subjects"][0]
    assert cleaned["nested"]["examName"] == "虚构测试数据：统一练习"

    # SSRF 正例：官方 HTTPS 图床域名且 DNS 解析为公网 IP
    def _fake_public_getaddrinfo(host, port, type=0):  # noqa: A002
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("140.205.94.189", 443))]

    monkeypatch.setattr(kb.socket, "getaddrinfo", _fake_public_getaddrinfo)
    assert kb.validate_safe_remote_card_url("https://test-bucket.oss-cn-beijing.aliyuncs.com/a.jpg")
    assert kb.validate_safe_remote_card_url("https://cdn.k12100.com/card.jpg")

    # SSRF 反例 1：非 HTTPS / 未知外域 / 含密码认证 / 非 443 端口
    for bad_url in (
        "http://cdn.k12100.com/card.jpg",
        "https://evil.example.com/card.jpg",
        "https://user:pass@cdn.k12100.com/card.jpg",
        "https://cdn.k12100.com:8443/card.jpg",
    ):
        with pytest.raises(HTTPException) as exc:
            kb.validate_safe_remote_card_url(bad_url)
        assert exc.value.status_code == 422
        assert exc.value.detail == "K12100_UNSAFE_CARD_URL"

    # SSRF 反例 2：白名单域名解析到回环/私网/云元数据 IP
    for private_ip in ("127.0.0.1", "10.0.0.5", "192.168.1.10", "169.254.169.254"):
        monkeypatch.setattr(
            kb.socket,
            "getaddrinfo",
            lambda host, port, type=0, ip=private_ip: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))],
        )
        with pytest.raises(HTTPException) as exc:
            kb.validate_safe_remote_card_url("https://cdn.k12100.com/card.jpg")
        assert exc.value.status_code == 422
        assert exc.value.detail == "K12100_UNSAFE_CARD_URL"


def test_import_bundle_series_alignment_locked_score_protection_and_ocr_draft_redline(
    tmp_path, client, auth, student_auth, monkeypatch
):
    monkeypatch.setenv("SHUTONG_PRIVATE_DIR", str(tmp_path / "private"))
    monkeypatch.delenv("SHUTONG_AI_API_KEY", raising=False)
    monkeypatch.delenv("SHUTONG_VISION_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    # 1. 创建既有未核对语文档案（含原卷 PDF）与既有已核对锁定数学档案（不同分值用于验证不覆写保护）
    ch_res = client.post(
        "/api/school-exams",
        json={
            "subject": "chinese",
            "title": "虚构测试数据 · 十月统一练习 · 语文",
            "exam_date": "2026-10-15",
            "earned_points": 0,
            "max_points": 100,
            "confirmed_by_user": False,
            "school_name": "虚构测试数据实验学校",
            "grade": "九年级",
            "exam_type": "monthly",
            "academic_year": "2026-2027",
            "term": "first",
            "series_title": "虚构测试数据 十月统一练习",
            "external_exam_id": "mock-exam-202610",
        },
        headers=auth,
    ).json()
    chinese_id = ch_res["id"]
    pdf_bytes = _make_fake_pdf_with_text()
    up_pdf = client.post(
        f"/api/school-exams/{chinese_id}/paper?filename=语文测试卷.pdf",
        content=pdf_bytes,
        headers={**auth, "Content-Type": "application/pdf"},
    )
    assert up_pdf.status_code == 201

    math_res = client.post(
        "/api/school-exams",
        json={
            "subject": "math",
            "title": "虚构测试数据 · 十月统一练习 · 数学",
            "exam_date": "2026-10-15",
            "earned_points": 88,
            "max_points": 100,
            "confirmed_by_user": True,
            "school_name": "虚构测试数据实验学校",
            "grade": "九年级",
            "exam_type": "monthly",
            "academic_year": "2026-2027",
            "term": "first",
            "series_title": "虚构测试数据 十月统一练习",
            "external_exam_id": "mock-exam-202610",
        },
        headers=auth,
    ).json()
    math_id = math_res["id"]

    # 2. 构造含语文（待确认更新总分 + 自然题号含默写/11（1））、数学（锁分保护冲突）、英语（自动补建 + JPEG 答题卡）的采集包
    valid_jpeg_b64 = base64.b64encode(_make_valid_jpeg_bytes()).decode("ascii")
    bundle = {
        "examName": "虚构测试数据 十月统一练习",
        "examDate": "2026-10-10",
        "schoolName": "虚构测试数据实验学校",
        "gradeName": "九年级",
        "examTypeName": "月考",
        "academicYear": "2026-2027",
        "termName": "第一学期",
        "seriesTitle": "虚构测试数据 十月统一练习",
        "examId": "mock-exam-202610",
        "studName": "应被脱敏的学生姓名",
        "subjects": [
            {
                "subjectName": "总报告",
                "score": 300,
                "fullScore": 400,
                "smallQuestions": [],
            },
            {
                "subjectName": "语文",
                "score": 63,
                "fullScore": 100,
                "smallQuestions": [
                    {"questionName": "11（1）", "questionTypeName": "解答", "difficultyName": "中等", "score": 2, "fullScore": 3},
                    {"questionName": "默写", "questionTypeName": "填空", "difficultyName": "容易", "score": 5, "fullScore": 6},
                    {"questionName": "1", "questionTypeName": "选择", "difficultyName": "容易", "score": 2, "fullScore": 2},
                ],
                "cardPages": [],
            },
            {
                "subjectName": "数学",
                "score": 70,
                "fullScore": 100,
                "smallQuestions": [
                    {"questionName": "2", "questionTypeName": "选择", "difficultyName": "容易", "score": 3, "fullScore": 3},
                    {"questionName": "1", "questionTypeName": "选择", "difficultyName": "容易", "score": 0, "fullScore": 3},
                ],
                "cardPages": [
                    {"page": 1, "questionVOS": [{"questionName": "1", "answer": "A", "questionAnswer": "B"}]}
                ],
            },
            {
                "subjectName": "英语",
                "score": 71,
                "fullScore": 100,
                "smallQuestions": [
                    {"questionName": "21", "questionTypeName": "单选", "difficultyName": "容易", "score": 0.5, "fullScore": 0.5},
                    {"questionName": "58", "questionTypeName": "写作", "difficultyName": "困难", "score": 7, "fullScore": 10},
                ],
                "card_images": [{"filename": "英语答_第1页.jpg", "data_base64": valid_jpeg_b64}],
            },
        ],
    }

    resp = client.post(
        "/api/school-exams/k12100-sync/import-bundle",
        json={
            "bundle": bundle,
            "target_exam_date": "2026-10-15",
            "confirm_total_scores": True,
            "use_ai": False,
        },
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["knowledge_evidence_created"] == 0
    assert body["totals"]["subjects_processed"] == 3
    assert body["totals"]["created_exams"] == 1
    assert body["totals"]["locked_conflicts"] == 1
    assert body["totals"]["attachments_uploaded"] == 1
    assert body["totals"]["drafts_created"] == 7

    by_subj = {s["subject"]: s for s in body["subjects"]}
    assert by_subj["chinese"]["score_status"] == "confirmed_now"
    assert by_subj["chinese"]["earned_points"] == 63.0
    assert by_subj["chinese"]["confirmed_by_user"] is True
    assert by_subj["chinese"]["stem_mode"] == "pdf_local_regex"

    assert by_subj["math"]["score_status"] == "locked_conflict"
    assert by_subj["math"]["earned_points"] == 88.0
    assert "保留原值" in (by_subj["math"]["warning"] or "")

    assert by_subj["english"]["score_status"] == "created_confirmed"
    assert by_subj["english"]["exam_date"] == "2026-10-15"
    assert "虚构测试数据" in by_subj["english"]["exam_title"]
    assert by_subj["english"]["attachments_uploaded"] == 1

    # 验证 INV-04：三科明细全为 ocr_draft 且未确认，学生端能力画像零污染
    eng_detail = client.get(f"/api/school-exams/{by_subj['english']['exam_id']}", headers=auth).json()
    assert len(eng_detail["attachments"]) == 1
    assert all(it["scoring_origin"] == "ocr_draft" and it["confirmed_by_user"] is False for it in eng_detail["items"])
    ch_detail = client.get(f"/api/school-exams/{chinese_id}", headers=auth).json()
    ch_labels = [it["question_label"] for it in ch_detail["items"]]
    assert set(ch_labels) == {"第1题", "默写", "第11题(1)"}
    math_detail = client.get(f"/api/school-exams/{math_id}", headers=auth).json()
    assert math_detail["earned_points"] == 88.0
    assert math_detail["confirmed_by_user"] is True
    for subj in ("math", "chinese", "english"):
        assert client.get(f"/api/guidance/profile?subject={subj}", headers=student_auth).json()["knowledge"] == []

    # 反例 1：禁用总分确认（confirm_total_scores=False）导入物理新场次时，必须保留待人工锁定状态
    phys_resp = client.post(
        "/api/school-exams/k12100-sync/import-bundle",
        json={
            "bundle": {
                "examName": "虚构测试数据：物理阶段测",
                "examDate": "2026-11-05",
                "subjects": [
                    {
                        "subjectName": "物理",
                        "score": 36,
                        "fullScore": 70,
                        "smallQuestions": [{"questionName": "1", "score": 2, "fullScore": 2}],
                    }
                ],
            },
            "confirm_total_scores": False,
            "use_ai": False,
        },
        headers=auth,
    )
    assert phys_resp.status_code == 200
    assert phys_resp.json()["subjects"][0]["score_status"] == "created_unconfirmed"
    assert phys_resp.json()["subjects"][0]["confirmed_by_user"] is False

    # 反例 2：伪造非 JPEG 字节的内嵌答题卡必须被拦截
    bad_card_resp = client.post(
        "/api/school-exams/k12100-sync/import-bundle",
        json={
            "bundle": {
                "examName": "虚构测试数据：坏卡包",
                "examDate": "2026-11-08",
                "subjects": [
                    {
                        "subjectName": "道德与法治",
                        "score": 33,
                        "fullScore": 50,
                        "smallQuestions": [{"questionName": "1", "score": 2, "fullScore": 2}],
                        "card_images": [{"filename": "fake.jpg", "data_base64": base64.b64encode(b"NOT_A_JPEG").decode("ascii")}],
                    }
                ],
            },
            "use_ai": False,
        },
        headers=auth,
    )
    assert bad_card_resp.status_code == 422
    assert bad_card_resp.json()["detail"] == "UNSUPPORTED_FILE_TYPE"


def test_runtime_status_permissions_isolation_and_single_job_mutex(client, auth, student_auth, tmp_path, monkeypatch):
    # 权限校验：未认证 401、学生令牌 403
    assert client.get("/api/school-exams/k12100-sync/status").status_code == 401
    assert client.get("/api/school-exams/k12100-sync/status", headers=student_auth).status_code == 403
    assert client.post("/api/school-exams/k12100-sync/jobs", json={}, headers=student_auth).status_code == 403

    cfg_dir = tmp_path / "k12cfg"
    cfg_dir.mkdir(mode=0o700)
    monkeypatch.setenv("SHUTONG_K12100_CONFIG_DIR", str(cfg_dir))
    monkeypatch.setenv("SHUTONG_PRIVATE_DIR", str(tmp_path / "private"))

    # 伪造最小仓库目录结构（不依赖 CI api-and-docs 是否安装 node_modules）
    fake_repo = tmp_path / "fake_repo"
    (fake_repo / "scripts").mkdir(parents=True)
    (fake_repo / "scripts" / "k12100_browser.mjs").write_text("// stub\n", encoding="utf-8")
    (fake_repo / "apps" / "web" / "node_modules" / "playwright-core").mkdir(parents=True)
    monkeypatch.setattr(kb, "resolve_repo_root", lambda *_args: fake_repo)

    # 隔离容器模式探测与 409 fail-closed
    monkeypatch.setenv("SHUTONG_DISABLE_LOCAL_K12100_RUNNER", "1")
    iso_status = client.get("/api/school-exams/k12100-sync/status", headers=auth)
    assert iso_status.status_code == 200
    assert iso_status.json()["can_run_local"] is False
    assert iso_status.json()["mode"] == "isolated_import_only"
    assert iso_status.json()["unavailable_code"] == "K12100_LOCAL_RUNNER_UNAVAILABLE"

    blocked_job = client.post("/api/school-exams/k12100-sync/jobs", json={}, headers=auth)
    assert blocked_job.status_code == 409
    assert blocked_job.json()["detail"] == "K12100_LOCAL_RUNNER_UNAVAILABLE"

    # 宿主机能力打开，但无凭据 -> 返回 409 K12100_CREDENTIALS_NOT_CONFIGURED
    monkeypatch.delenv("SHUTONG_DISABLE_LOCAL_K12100_RUNNER", raising=False)
    monkeypatch.setattr(kb, "_is_isolated_container", lambda: False)
    monkeypatch.setattr(kb, "_find_node_binary", lambda: "/usr/local/bin/node")
    no_cred = client.post("/api/school-exams/k12100-sync/jobs", json={}, headers=auth)
    assert no_cred.status_code == 409
    assert no_cred.json()["detail"] == "K12100_CREDENTIALS_NOT_CONFIGURED"

    # 写入合规 0700/0600 凭据并模拟采集门闩，验证并发互斥锁（409 K12100_SYNC_ALREADY_RUNNING）与脱敏不泄密
    env_file = cfg_dir / "k12100.env"
    env_file.write_text("K12100_USERNAME=25999stu\nK12100_PASSWORD=TopSecretPassword999\n", encoding="utf-8")
    os.chmod(cfg_dir, 0o700)
    os.chmod(env_file, 0o600)

    host_status = client.get("/api/school-exams/k12100-sync/status", headers=auth)
    assert host_status.status_code == 200
    status_json = host_status.json()
    assert status_json["can_run_local"] is True
    assert status_json["credentials"]["username_masked"] == "25***u"
    assert status_json["recommended_cli_command"] == "uv run python scripts/k12100_sync.py collect --env development"
    assert "~/.config/shutong" not in status_json["recommended_cli_command"]
    assert "TopSecretPassword999" not in host_status.text
    assert "25999stu" not in host_status.text

    entered = threading.Event()
    release = threading.Event()

    def _mock_collect(**_kwargs):
        entered.set()
        release.wait(timeout=5)
        return {
            "examName": "虚构测试数据：任务测试",
            "examDate": "2026-11-10",
            "subjects": [
                {
                    "subjectName": "物理",
                    "score": 65,
                    "fullScore": 70,
                    "smallQuestions": [{"questionName": "1", "score": 2, "fullScore": 2}],
                }
            ],
        }

    monkeypatch.setattr(kb, "_collect_with_browser", _mock_collect)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("SHUTONG_AI_API_KEY", raising=False)

    start_resp = client.post("/api/school-exams/k12100-sync/jobs", json={"use_ai": False}, headers=auth)
    assert start_resp.status_code == 202
    job_id = start_resp.json()["job_id"]
    assert entered.wait(timeout=3)

    # 第二个并发启动请求必须被单任务互斥锁拦截
    second_resp = client.post("/api/school-exams/k12100-sync/jobs", json={"use_ai": False}, headers=auth)
    assert second_resp.status_code == 409
    assert second_resp.json()["detail"] == "K12100_SYNC_ALREADY_RUNNING"

    # 放行第一个任务并轮询至 completed
    release.set()
    final_job = None
    for _ in range(40):
        poll = client.get(f"/api/school-exams/k12100-sync/jobs/{job_id}", headers=auth)
        assert poll.status_code == 200
        if poll.json()["state"] in {"completed", "failed"}:
            final_job = poll.json()
            break
        time.sleep(0.05)

    assert final_job is not None
    assert final_job["state"] == "completed"
    assert final_job["result"]["totals"]["drafts_created"] == 1
    assert final_job["result"]["subjects"][0]["subject"] == "physics"

    # 风控熔断场景验证：采集抛 CIRCUIT_BREAKER 时任务状态 cleanly 转入 failed
    def _mock_breaker(**_kwargs):
        raise RuntimeError("K12100_CIRCUIT_BREAKER: 检测到图形验证码，已立即停止")

    monkeypatch.setattr(kb, "_collect_with_browser", _mock_breaker)
    fail_start = client.post("/api/school-exams/k12100-sync/jobs", json={"use_ai": False}, headers=auth)
    assert fail_start.status_code == 202
    fail_id = fail_start.json()["job_id"]
    failed_job = None
    for _ in range(40):
        poll = client.get(f"/api/school-exams/k12100-sync/jobs/{fail_id}", headers=auth)
        if poll.json()["state"] in {"completed", "failed"}:
            failed_job = poll.json()
            break
        time.sleep(0.05)
    assert failed_job is not None
    assert failed_job["state"] == "failed"
    assert failed_job["error_code"] == "K12100_CIRCUIT_BREAKER"

    assert client.get("/api/school-exams/k12100-sync/jobs/nonexistent-id", headers=auth).status_code == 404


def test_pdf_deepseek_stem_extraction_batches_when_configured(tmp_path, client, auth, monkeypatch):
    monkeypatch.setenv("SHUTONG_PRIVATE_DIR", str(tmp_path / "private"))
    ex = client.post(
        "/api/school-exams",
        json={
            "subject": "chinese",
            "title": "虚构测试数据：分批提干测试",
            "exam_date": "2026-11-12",
            "earned_points": 80,
            "max_points": 100,
            "confirmed_by_user": False,
            "school_name": "虚构测试数据实验学校",
            "grade": "九年级",
            "exam_type": "midterm",
            "academic_year": "2026-2027",
            "term": "first",
            "series_title": "虚构测试数据 期中考试",
        },
        headers=auth,
    ).json()
    up = client.post(
        f"/api/school-exams/{ex['id']}/paper?filename=语文卷.pdf",
        content=_make_fake_pdf_with_text(),
        headers={**auth, "Content-Type": "application/pdf"},
    )
    assert up.status_code == 201

    calls: list[int] = []
    monkeypatch.setattr(
        parser,
        "load_vision_config",
        lambda require_key=False: parser.VisionParserConfig(
            base_url="https://api.deepseek.com",
            api_key="sk-fake",
            vision_model="deepseek-flash",
            text_model="deepseek-chat",
            timeout_seconds=30.0,
        ),
    )

    def _fake_deepseek(cfg, *, model, messages, max_tokens=4096):
        prompt = messages[-1]["content"]
        # 仅统计 PDF 提干分批请求，验证超过 16 题时按 12 题分片调用
        if '"stems"' in prompt:
            calls.append(len(prompt))
            stems = [{"question_label": f"第{i}题", "stem_text": f"题目{i}真实设问"} for i in range(1, 21)]
            return {"stems": stems}
        return {"items": []}

    monkeypatch.setattr(parser, "_post_deepseek_json", _fake_deepseek)

    # 通过 import-bundle 驱动真实数据库附件抽取流程
    small_qs = [{"questionName": str(i), "score": 1, "fullScore": 1} for i in range(1, 21)]
    resp = client.post(
        "/api/school-exams/k12100-sync/import-bundle",
        json={
            "bundle": {
                "examName": "虚构测试数据：分批提干测试",
                "examDate": "2026-11-12",
                "schoolName": "虚构测试数据实验学校",
                "gradeName": "九年级",
                "examTypeName": "期中",
                "academicYear": "2026-2027",
                "termName": "第一学期",
                "seriesTitle": "虚构测试数据 期中考试",
                "subjects": [{"subjectName": "语文", "score": 20, "fullScore": 20, "smallQuestions": small_qs}],
            },
            "use_ai": True,
            "target_exam_date": "2026-11-12",
        },
        headers=auth,
    )
    # _post_deepseek_json 同时服务于 PDF 提干（2 批）和外部逐题匹配（2 批），mock 会返回合法字典，重点断言 >1 批
    assert resp.status_code == 200
    assert len(calls) >= 2
    assert resp.json()["subjects"][0]["stem_mode"] == "pdf_deepseek"

def test_validate_collected_bundle_distinguishes_empty_from_invalid():
    with pytest.raises(RuntimeError, match="K12100_NO_EXAMS"):
        kb.validate_collected_bundle({"status": "collected", "exams": []})
    with pytest.raises(RuntimeError, match="K12100_NO_SUBJECTS"):
        kb.validate_collected_bundle({"status": "collected", "exams": [{"subjects": []}]})
    with pytest.raises(RuntimeError, match="K12100_INVALID_BUNDLE"):
        kb.validate_collected_bundle([])
    valid = {"status": "collected", "exams": [{"subjects": [{"subjectName": "数学"}]}]}
    assert kb.validate_collected_bundle(valid) is valid
