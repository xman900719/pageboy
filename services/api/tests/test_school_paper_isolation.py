"""ST-006：使用虚构测试数据验证私人校卷附件与内容接口的隔离（AC-SEC-01）。"""
from contextlib import contextmanager
from hashlib import sha256
from io import BytesIO
import json
import re

import pytest
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select

from shutong import models as m
from shutong.database import get_db
from shutong.main import app
from shutong.private_files import private_root, school_exams_root


@contextmanager
def database():
    yield from app.dependency_overrides[get_db]()


@pytest.fixture
def private_dir(tmp_path, monkeypatch):
    root = tmp_path / "private"
    monkeypatch.setenv("SHUTONG_PRIVATE_DIR", str(root))
    return root


def make_exam(client, auth, **overrides):
    body = {"subject": "math", "title": "虚构测试数据：周测", "exam_date": "2026-10-20",
            "earned_points": 72, "max_points": 100, "confirmed_by_user": True}
    body.update(overrides)
    response = client.post("/api/school-exams", json=body, headers=auth)
    assert response.status_code == 201
    return response.json()["id"]


def png_bytes():
    # 与 test_ingestion.py 的合成图同构：PIL 现场生成，绝不含真实校卷内容。
    image = Image.new("RGB", (1000, 200), "white")
    ImageDraw.Draw(image).text((20, 40), "SYNTHETIC TEST DATA", fill="black", font=ImageFont.load_default(size=48))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def upload_paper(client, auth, exam_id, data=None, media_type="image/png", filename="虚构测试数据-周测卷.png", expected_sha256=None):
    # 镜像 ST-003 附件上传调用约定：filename 走查询参数、原始字节做请求体、Content-Type 标识媒体类型。
    params = {"filename": filename}
    if expected_sha256 is not None:
        params["expected_sha256"] = expected_sha256
    return client.post(f"/api/school-exams/{exam_id}/paper", params=params,
                       content=png_bytes() if data is None else data,
                       headers={**auth, "Content-Type": media_type})


def blob_count(root):
    return len(list(root.iterdir())) if root.is_dir() else 0


def test_paper_upload_stores_privately_without_storage_key(client, auth, private_dir):
    exam_id = make_exam(client, auth)
    png = png_bytes()
    before_private = blob_count(private_dir)
    attached = upload_paper(client, auth, exam_id, data=png)
    assert attached.status_code == 201
    meta = attached.json()
    assert set(meta) == {"id", "filename", "media_type", "sha256", "byte_size", "created_at"}
    assert "storage_key" not in meta  # AC-SEC-01：存储键不进 HTTP 响应
    assert "relative_path" not in meta
    assert meta["filename"] == "虚构测试数据-周测卷.png" and meta["media_type"] == "image/png"
    assert re.fullmatch(r"[0-9a-f]{64}", meta["sha256"]) and meta["sha256"] == sha256(png).hexdigest()
    assert meta["byte_size"] == len(png) and meta["created_at"]
    assert private_root() == private_dir.resolve()
    assert blob_count(private_dir) == before_private  # 校考原卷不再写入 data/attachments
    with database() as db:
        exam = db.get(m.SchoolExam, exam_id)
        assert exam is not None and exam.archive_dir
        exam_paper_dir = school_exams_root() / exam.archive_dir / "exam-paper"
        answer_sheet_dir = school_exams_root() / exam.archive_dir / "answer-sheet"
        assert exam_paper_dir.is_dir() and answer_sheet_dir.is_dir()
        files_in_dir = list(exam_paper_dir.iterdir())
        assert len(files_in_dir) == 1
        assert files_in_dir[0].read_bytes() == png
        assert files_in_dir[0].stat().st_mode & 0o777 == 0o600


def test_create_all_subject_exam_defaults_earned_to_max_and_cleans_dirs(client, auth, private_dir):
    created = client.post(
        "/api/school-exams",
        json={
            "title": "虚构测试数据：全科月考",
            "exam_date": "2026-11",
            "max_points": 120,
            "confirmed_by_user": False,
        },
        headers=auth,
    )
    assert created.status_code == 201, created.text
    exam_id = created.json()["id"]
    assert created.json()["subject"] == "all"

    detail = client.get(f"/api/school-exams/{exam_id}", headers=auth)
    assert detail.status_code == 200
    assert detail.json()["earned_points"] == 120
    assert detail.json()["max_points"] == 120
    assert detail.json()["subject"] == "all"

    math_list = client.get("/api/school-exams?subject=math", headers=auth)
    assert math_list.status_code == 200
    assert any(item["id"] == exam_id and item["subject"] == "all" for item in math_list.json())

    with database() as db:
        archive_dir = db.get(m.SchoolExam, exam_id).archive_dir
    archive_path = school_exams_root() / archive_dir
    assert (archive_path / "exam-paper").is_dir()
    assert (archive_path / "answer-sheet").is_dir()

    uploaded = upload_paper(client, auth, exam_id)
    assert uploaded.status_code == 201
    assert len(list((archive_path / "exam-paper").iterdir())) == 1

    deleted = client.delete(f"/api/school-exams/{exam_id}?confirm=true", headers=auth)
    assert deleted.status_code == 200
    assert not archive_path.exists()


def test_paper_upload_validates_type(client, auth, private_dir):
    exam_id = make_exam(client, auth)
    png = png_bytes()
    mismatch = upload_paper(client, auth, exam_id, data=png, media_type="application/pdf")
    assert mismatch.status_code == 422 and mismatch.json()["detail"] == "FILE_TYPE_MISMATCH"
    unsupported = upload_paper(client, auth, exam_id, data=png, media_type="text/plain")
    assert unsupported.status_code == 415 and unsupported.json()["detail"] == "UNSUPPORTED_FILE_TYPE"
    empty = upload_paper(client, auth, exam_id, data=b"")
    assert empty.status_code == 422 and empty.json()["detail"] == "INVALID_FILE_SIZE"
    assert blob_count(private_dir) == 0  # 无效上传不落盘


def test_paper_upload_stream_cap_and_hash_mismatch(client, auth, private_dir):
    # Gate 整改（MINOR#1）：413 流式上限与 UPLOAD_HASH_MISMATCH 是学校端点独有的重复代码路径，
    # 不得只依赖 test_ingestion.py 的同型覆盖。
    exam_id = make_exam(client, auth)
    oversized = upload_paper(client, auth, exam_id, data=b"x" * (35 * 1024 * 1024 + 1))
    assert oversized.status_code == 413 and oversized.json()["detail"] == "INVALID_FILE_SIZE"
    png = png_bytes()
    mismatch = upload_paper(client, auth, exam_id, data=png, expected_sha256="0" * 64)
    assert mismatch.status_code == 422 and mismatch.json()["detail"] == "UPLOAD_HASH_MISMATCH"
    assert blob_count(private_dir) == 0  # 两种失败均不落盘
    matched = upload_paper(client, auth, exam_id, data=png, expected_sha256=sha256(png).hexdigest())
    assert matched.status_code == 201  # 提供正确哈希时正常入库


def test_paper_is_invisible_to_content_pipeline(client, auth, student_auth, published, private_dir):
    exam_id = make_exam(client, auth)
    attached = upload_paper(client, auth, exam_id)
    assert attached.status_code == 201
    attachment_id = attached.json()["id"]
    ledger = client.get("/api/admin/sources", headers=auth)
    assert ledger.status_code == 200
    assert attachment_id not in ledger.text  # 校卷附件不进内容台账
    assert client.get(f"/api/admin/sources/{attachment_id}", headers=auth).status_code == 404
    draft = client.post("/api/admin/questions", json={
        "source_document_id": attachment_id, "stem": "虚构测试数据：1+1=?", "options": ["A. 1", "B. 2"],
        "correct_answer": "B", "knowledge_ids": ["math.arithmetic"], "max_points": 2}, headers=auth)
    assert draft.status_code == 404  # 校卷附件 id 不是 source_documents id，无法被题目草稿引用
    served = client.get("/api/practice/next?subject=math", headers=student_auth)
    assert served.status_code == 200 and served.json()["question_version_id"] in published


def test_no_route_serves_paper_bytes(client, auth, private_dir):
    exam_id = make_exam(client, auth)
    attached = upload_paper(client, auth, exam_id)
    assert attached.status_code == 201
    attachment_id = attached.json()["id"]
    for path in (f"/api/school-exams/{exam_id}/paper/{attachment_id}",
                 f"/api/school-exams/{exam_id}/attachments/{attachment_id}",
                 f"/api/admin/attachments/{attachment_id}",
                 f"/api/admin/attachments/{attachment_id}/download"):
        assert client.get(path, headers=auth).status_code == 404, path
    # /paper 仅注册 POST 上传路由：实现前为 404（无路由），实现后 GET 为 405（方法不允许）；
    # 两种情形都不存在返回校卷字节的读取路由。
    paper = client.get(f"/api/school-exams/{exam_id}/paper", headers=auth)
    assert paper.status_code in (404, 405)


def test_paper_ownership_and_auth(client, auth, private_dir):
    exam_id = make_exam(client, auth)
    assert upload_paper(client, {}, exam_id).status_code == 401
    assert upload_paper(client, auth, "missing-exam").status_code == 404
    bad_token = upload_paper(client, {"Authorization": "Bearer not-the-owner-token"}, exam_id)
    assert bad_token.status_code == 401


def test_exam_detail_lists_paper_metadata_only(client, auth, private_dir):
    exam_id = make_exam(client, auth)
    attached = upload_paper(client, auth, exam_id)
    assert attached.status_code == 201
    attachment_id = attached.json()["id"]
    detail = client.get(f"/api/school-exams/{exam_id}", headers=auth)
    assert detail.status_code == 200
    body = detail.json()
    assert len(body["attachments"]) == 1
    meta = body["attachments"][0]
    for key in ("id", "filename", "media_type", "sha256", "byte_size", "created_at"):
        assert key in meta, key
    assert meta["id"] == attachment_id
    with database() as db:
        keys = db.scalars(select(m.SchoolPaperAttachment.storage_key)
                          .where(m.SchoolPaperAttachment.id == attachment_id)).all()
    assert len(keys) == 1 and re.fullmatch(r"[0-9a-f]{32}", keys[0])  # 键确实存在于数据库
    assert keys[0] not in json.dumps(body)  # 但从不离开 API
    assert "storage_key" not in json.dumps(body)


def test_k12100_import_bundle_writes_answer_sheets_to_archive_dir(client, auth, private_dir):
    import base64

    created = client.post(
        "/api/school-exams",
        json={
            "title": "虚构测试数据：十一月全科统练",
            "exam_date": "2026-11",
            "max_points": 100,
            "confirmed_by_user": False,
        },
        headers=auth,
    )
    assert created.status_code == 201
    archive_exam_id = created.json()["id"]

    jpg_buf = BytesIO()
    Image.new("RGB", (40, 40), "white").save(jpg_buf, format="JPEG")
    card_b64 = base64.b64encode(jpg_buf.getvalue()).decode("ascii")

    bundle = {
        "schema_version": 1,
        "exams": [
            {
                "exam_title": "虚构测试数据：十一月全科统练",
                "exam_date": "2026-11-12",
                "subjects": [
                    {
                        "subject": "math",
                        "subject_cn": "数学",
                        "earned_points": 88,
                        "max_points": 100,
                        "identity": {
                            "exam_date": "2026-11-12",
                            "academic_year": "2026-2027",
                            "grade": "9",
                            "exam_type": "unified_practice",
                            "series_title": "虚构测试数据：十一月全科统练",
                        },
                        "card_images": [
                            {"filename": "数学答题卡_1.jpg", "data_base64": card_b64}
                        ],
                        "small_questions": [
                            {"question_label": "第1题", "earned_points": 4, "max_points": 4}
                        ],
                    }
                ],
            }
        ],
    }

    res = client.post(
        "/api/school-exams/k12100-sync/import-bundle",
        json={
            "bundle": bundle,
            "archive_exam_id": archive_exam_id,
            "upload_missing_cards": True,
            "extract_existing_pdfs": False,
        },
        headers=auth,
    )
    assert res.status_code == 200, res.text
    assert res.json()["totals"]["attachments_uploaded"] == 1

    with database() as db:
        archive_exam = db.get(m.SchoolExam, archive_exam_id)
        archive_dir = archive_exam.archive_dir
        assert archive_dir
    answer_sheet_dir = school_exams_root() / archive_dir / "answer-sheet"
    assert answer_sheet_dir.is_dir()
    saved_cards = list(answer_sheet_dir.iterdir())
    assert len(saved_cards) == 1
    assert saved_cards[0].read_bytes() == jpg_buf.getvalue()
    assert blob_count(private_dir) == 0  # 答题卡不落入 data/attachments


def test_sync_center_and_scan_target_selected_archive_exam_paper_dir(client, auth, private_dir):
    created = client.post(
        "/api/school-exams",
        json={
            "title": "虚构测试数据：扫描目录检验",
            "exam_date": "2026-11",
            "max_points": 100,
            "confirmed_by_user": False,
        },
        headers=auth,
    )
    assert created.status_code == 201
    exam_id = created.json()["id"]

    uploaded = upload_paper(client, auth, exam_id, filename="虚构测试数据-扫描原卷.png")
    assert uploaded.status_code == 201

    center = client.get(f"/api/school-exams/sync-center?exam_id={exam_id}", headers=auth)
    assert center.status_code == 200
    assert center.json()["source"]["directory_display"].endswith("/exam-paper")

    scanned = client.post(
        "/api/school-exams/pipeline/scan",
        json={"exam_id": exam_id},
        headers=auth,
    )
    assert scanned.status_code == 200, scanned.text
    assert scanned.json()["run"]["discovered_count"] == 1
    assert scanned.json()["papers"][0]["filename"] == "虚构测试数据-扫描原卷.png"

    with database() as db:
        archive_dir = db.get(m.SchoolExam, exam_id).archive_dir
    archive_path = school_exams_root() / archive_dir
    assert archive_path.is_dir()

    deleted = client.delete(f"/api/school-exams/{exam_id}?confirm=true", headers=auth)
    assert deleted.status_code == 200
    assert not archive_path.exists()
    center_after = client.get("/api/school-exams/sync-center", headers=auth)
    assert center_after.status_code == 200
    assert center_after.json()["papers"] == []
